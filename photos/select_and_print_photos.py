#!/usr/bin/env python3
"""
Weekly Photo Selector and Printer

Finds photos taken in the past week on the NAS, rates them with a local
Ollama vision model, and prints the best ones on the Canon PIXMA G620.

Settings live in ~/weekly-photo-selector/config.json (see DEFAULT_CONFIG);
any key left out uses the default below.
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from ollama_client import HEIF_SUPPORTED, OllamaClient, OllamaError, encode_image_base64

SYSTEM_DIR = Path.home() / "weekly-photo-selector"
CONFIG_PATH = Path(os.environ.get("PHOTO_SELECTOR_CONFIG", SYSTEM_DIR / "config.json"))

DEFAULT_CONFIG = {
    "photo_dirs": ["~/nas-home/Photos/MobileBackup", "~/nas-home/Photos/phockup"],
    # Tried in order; only models that can actually see images are listed.
    "vision_models": ["llama3.2-vision:latest", "llava:latest"],
    "ollama_url": "http://localhost:11434",
    "metadata_dir": str(SYSTEM_DIR / "selections_metadata"),
    "log_dir": str(SYSTEM_DIR / "logs"),
    # Set by setup_canon_printer.sh; check with `lpstat -p`.
    "printer_name": "Canon_G620",
    # Passed to lpr as `-o key=value`; null values are skipped.
    # See `lpoptions -p <printer> -l` for valid values, e.g. media "na_index-4x6_4x6in".
    "print_options": {"fit-to-page": "true", "print-quality": "5", "media": None},
    "max_photos_to_select": 5,
    "family_photo_focus": True,
    "min_family_score": 6,
    "prefer_multiple_people": True,
    "boost_children_photos": True,
    # Photos taken within this many seconds of an already-selected one are
    # treated as part of the same burst and skipped.
    "burst_window_seconds": 10,
    "skip_previously_printed": True,
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif"}

# EXIF tag ids
EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME_DIGITIZED = 36868
TAG_DATETIME = 306

logger = logging.getLogger("photo_selector")


@dataclass
class Photo:
    path: Path
    taken: datetime
    sha256: str = ""
    rating: Dict = field(default_factory=dict)

    @property
    def score(self) -> int:
        return self.rating.get("score", 0)


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        with open(path) as f:
            user_config = json.load(f)
        unknown = set(user_config) - set(DEFAULT_CONFIG)
        if unknown:
            raise ValueError(f"Unknown keys in {path}: {sorted(unknown)}")
        for key, value in user_config.items():
            # Merge dict settings so e.g. {"print_options": {"media": ...}} keeps the other print defaults.
            if isinstance(DEFAULT_CONFIG[key], dict) and isinstance(value, dict):
                config[key] = {**DEFAULT_CONFIG[key], **value}
            else:
                config[key] = value
    if os.environ.get("PHOTO_SELECTOR_PRINTER"):
        config["printer_name"] = os.environ["PHOTO_SELECTOR_PRINTER"]
    return config


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: List[logging.Handler] = [logging.FileHandler(log_dir / "photo_selector.log")]
    # Only echo to the console when run interactively; under launchd stdout is
    # redirected to a log file and would duplicate every line.
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def to_score(value, default: Optional[int] = None) -> Optional[int]:
    """Coerce a model-supplied score ("8", 8.0, 8) to an int in 1..10."""
    try:
        return max(1, min(10, round(float(value))))
    except (TypeError, ValueError):
        return default


def to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


FAMILY_PROMPT = """Rate this photo on a scale of 1-10 for family memory value and printing quality. Consider:
1. Family content and emotional significance:
   - Clear faces of family members (especially children)
   - Genuine emotions, smiles, laughter, or meaningful expressions
   - Family interactions, bonding moments, milestones
   - Special occasions, holidays, vacations, everyday precious moments
2. Memory worthiness:
   - Will this be treasured in 5-10 years?
   - Does it capture personality or a special moment in time?
3. Print quality:
   - Good focus and lighting on faces
   - Composition that works well for physical printing
   - Not blurry, overexposed, or technically poor

Give LOWER scores (1-4) to photos without clear people, blurry faces, poor
lighting on people, screenshots, memes, documents, or generic landscape/food
photos without family context.

Give HIGHER scores (7-10) to clear, well-lit photos of family members,
emotional moments, celebrations, milestones, and images that tell a family story.

Respond with JSON only, using numbers for scores:
{
    "score": <integer 1-10>,
    "reasoning": "<brief explanation focusing on family memory value>",
    "family_content": <integer 1-10>,
    "emotional_impact": <integer 1-10>,
    "print_quality": <integer 1-10>,
    "memory_worthiness": <integer 1-10>,
    "people_count": <integer number of people clearly visible>,
    "children_present": <true or false>
}"""

GENERAL_PROMPT = """Rate this photo on a scale of 1-10 for printing quality and emotional impact. Consider:
1. Technical quality (focus, exposure, composition)
2. Emotional impact and memorability
3. Print worthiness (how good it would look printed)
4. Uniqueness and interest

Respond with JSON only, using numbers for scores:
{
    "score": <integer 1-10>,
    "reasoning": "<brief explanation>",
    "technical_quality": <integer 1-10>,
    "emotional_impact": <integer 1-10>,
    "print_worthiness": <integer 1-10>
}"""


class PhotoSelector:
    def __init__(self, config: dict, test_mode: bool = False):
        self.config = config
        self.test_mode = test_mode
        self.metadata_dir = Path(os.path.expanduser(config["metadata_dir"]))
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.metadata_dir / "printed_history.json"
        self.ollama = OllamaClient(config["ollama_url"])
        self.model: Optional[str] = None
        self.week_start, self.week_end = self.get_week_range()
        self.attempted = 0  # photos sent for rating in the last select_top_photos() call

    # ----- collecting -------------------------------------------------------

    @staticmethod
    def get_week_range(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        """The 7 full days ending at midnight tonight.

        Run on Sunday this covers Monday 00:00 through Sunday 23:59, so weekly
        runs neither overlap nor leave gaps.
        """
        now = now or datetime.now()
        week_end = datetime(now.year, now.month, now.day) + timedelta(days=1)
        week_start = week_end - timedelta(days=7)
        return week_start, week_end

    @staticmethod
    def get_image_date(image_path: Path) -> datetime:
        """Capture date from EXIF (DateTimeOriginal preferred), else file mtime."""
        try:
            with Image.open(image_path) as img:
                exif = img.getexif()
                sub = exif.get_ifd(EXIF_IFD)
                for value in (
                    sub.get(TAG_DATETIME_ORIGINAL),
                    sub.get(TAG_DATETIME_DIGITIZED),
                    exif.get(TAG_DATETIME),
                ):
                    if value:
                        return datetime.strptime(str(value).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
        except Exception as e:
            logger.debug(f"No usable EXIF date in {image_path}: {e}")
        return datetime.fromtimestamp(image_path.stat().st_mtime)

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def collect_weekly_photos(self) -> List[Photo]:
        """Photos taken during the week, with exact duplicates across folders removed."""
        logger.info(
            f"Selecting photos from {self.week_start:%Y-%m-%d} to "
            f"{self.week_end - timedelta(days=1):%Y-%m-%d}"
        )
        if not HEIF_SUPPORTED:
            logger.warning("pillow-heif not installed: HEIC photos will be skipped")

        start_ts = self.week_start.timestamp()
        photos: List[Photo] = []
        seen_hashes = set()

        for photo_dir_str in self.config["photo_dirs"]:
            photo_dir = Path(os.path.expanduser(photo_dir_str))
            if not photo_dir.exists():
                logger.warning(f"Photo directory does not exist (is the NAS mounted?): {photo_dir}")
                continue
            logger.info(f"Scanning {photo_dir}")

            for image_path in photo_dir.rglob("*"):
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS or image_path.name.startswith("."):
                    continue
                try:
                    # A file can't have been taken after it was last written, so
                    # anything not modified this week can be skipped without
                    # opening it over the network.
                    if image_path.stat().st_mtime < start_ts:
                        continue
                    taken = self.get_image_date(image_path)
                    if not (self.week_start <= taken < self.week_end):
                        continue
                    sha = self.file_hash(image_path)
                    if sha in seen_hashes:
                        logger.debug(f"Skipping duplicate {image_path}")
                        continue
                    seen_hashes.add(sha)
                    photos.append(Photo(image_path, taken, sha))
                except Exception as e:
                    logger.warning(f"Error processing {image_path}: {e}")

        logger.info(f"Found {len(photos)} unique photos from the past week")
        return photos

    # ----- rating -----------------------------------------------------------

    def rate_photo(self, photo: Photo) -> Optional[Dict]:
        """Return a normalized rating dict, or None if the photo couldn't be rated."""
        try:
            image_b64 = encode_image_base64(photo.path)
        except Exception as e:
            logger.warning(f"Could not open {photo.path.name}: {e}")
            return None

        prompt = FAMILY_PROMPT if self.config["family_photo_focus"] else GENERAL_PROMPT
        try:
            raw = self.ollama.generate_json(self.model, prompt, image_b64)
        except OllamaError as e:
            logger.warning(f"Could not rate {photo.path.name}: {e}")
            return None

        score = to_score(raw.get("score"))
        if score is None:
            logger.warning(f"No valid score for {photo.path.name}: {raw}")
            return None

        rating = dict(raw)
        rating["score"] = score
        rating["reasoning"] = str(raw.get("reasoning") or "")
        for key in ("family_content", "emotional_impact", "print_quality", "memory_worthiness",
                    "technical_quality", "print_worthiness"):
            if key in raw:
                rating[key] = to_score(raw[key])

        if self.config["family_photo_focus"]:
            rating = self.apply_family_adjustments(rating)

        logger.info(f"Rated {photo.path.name}: {rating['score']}/10")
        return rating

    def apply_family_adjustments(self, rating: Dict) -> Dict:
        """Cap non-family photos and boost group/children photos, using the model's structured fields."""
        family_content = rating.get("family_content") or 5
        if family_content < self.config["min_family_score"]:
            rating["below_family_threshold"] = True
            rating["reasoning"] += f" (excluded: family content {family_content} < {self.config['min_family_score']})"
            return rating

        boost, reasons = 0, []
        try:
            people = int(float(rating.get("people_count", 0)))
        except (TypeError, ValueError):
            people = 0
        if self.config["prefer_multiple_people"] and people >= 2:
            boost += 1
            reasons.append(f"{people} people")
        if self.config["boost_children_photos"] and to_bool(rating.get("children_present")):
            boost += 1
            reasons.append("children present")

        if boost:
            rating["score"] = min(rating["score"] + boost, 10)
            rating["reasoning"] += f" (boosted +{boost} for: {', '.join(reasons)})"
        return rating

    # ----- selecting --------------------------------------------------------

    def load_printed_history(self) -> Dict[str, datetime]:
        """sha256 -> capture time of every photo printed so far."""
        if not self.history_file.exists():
            return {}
        try:
            raw = json.loads(self.history_file.read_text())
            return {sha: datetime.fromisoformat(taken) for sha, taken in raw.items()}
        except (OSError, ValueError, AttributeError) as e:
            logger.warning(f"Could not read {self.history_file}: {e}")
            return {}

    def record_printed(self, photos: List[Photo]) -> None:
        history = self.load_printed_history()
        history.update({p.sha256: p.taken for p in photos})
        data = {sha: taken.isoformat() for sha, taken in sorted(history.items())}
        self.history_file.write_text(json.dumps(data, indent=2))

    def select_top_photos(self, photos: List[Photo]) -> Tuple[List[Photo], int]:
        """Rate photos and pick the best, skipping bursts and past prints.

        Returns (selected photos, number successfully rated).
        """
        burst = timedelta(seconds=self.config["burst_window_seconds"])
        printed_times: List[datetime] = []
        if self.config["skip_previously_printed"]:
            printed = self.load_printed_history()
            printed_times = list(printed.values())
            before = len(photos)
            photos = [
                p for p in photos
                if p.sha256 not in printed and not any(abs(p.taken - t) <= burst for t in printed_times)
            ]
            if before != len(photos):
                logger.info(f"Skipping {before - len(photos)} photos already printed (or from the same burst)")
        self.attempted = len(photos)
        if not photos:
            logger.info("Nothing new to rate")
            return [], 0

        logger.info(f"Rating {len(photos)} photos with {self.model}...")
        rated: List[Photo] = []
        for i, photo in enumerate(photos, 1):
            logger.info(f"Processing photo {i}/{len(photos)}: {photo.path.name}")
            rating = self.rate_photo(photo)
            if rating is not None:
                photo.rating = rating
                rated.append(photo)

        if not rated:
            logger.warning("No photos received valid ratings")
            return [], 0
        if len(rated) < len(photos):
            logger.warning(f"{len(photos) - len(rated)} photos could not be rated and were left out")

        eligible = [p for p in rated if not p.rating.get("below_family_threshold")]
        if len(eligible) < len(rated):
            logger.info(f"{len(rated) - len(eligible)} photos excluded for low family content")

        selected: List[Photo] = []
        for photo in sorted(eligible, key=lambda p: p.score, reverse=True):
            if any(abs(photo.taken - s.taken) <= burst for s in selected):
                logger.debug(f"Skipping {photo.path.name}: same burst as a selected photo")
                continue
            selected.append(photo)
            if len(selected) == self.config["max_photos_to_select"]:
                break

        logger.info(f"Selected top {len(selected)} photos:")
        for i, photo in enumerate(selected, 1):
            logger.info(f"  {i}. {photo.path} - Score: {photo.score}/10")
            logger.info(f"     Reasoning: {photo.rating.get('reasoning')}")
        return selected, len(rated)

    def save_selection_metadata(self, selected: List[Photo], found: int, rated: int) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = self.metadata_dir / f"selection_{timestamp}.json"
        summary = {
            "selection_date": timestamp,
            "week_range": f"{self.week_start:%Y-%m-%d} to {self.week_end - timedelta(days=1):%Y-%m-%d}",
            "model": self.model,
            "test_mode": self.test_mode,
            "total_photos_found": found,
            "total_photos_rated": rated,
            "selected_photos": [
                {
                    "rank": i,
                    "original_path": str(p.path),
                    "filename": p.path.name,
                    "taken": p.taken.isoformat(),
                    "sha256": p.sha256,
                    "rating": p.rating,
                }
                for i, p in enumerate(selected, 1)
            ],
        }
        summary_file.write_text(json.dumps(summary, indent=2))
        logger.info(f"Selection metadata saved to: {summary_file}")
        return summary_file

    # ----- printing ---------------------------------------------------------

    def printer_ready(self) -> bool:
        printer = self.config["printer_name"]
        status = subprocess.run(["lpstat", "-p", printer], capture_output=True, text=True)
        if status.returncode != 0:
            logger.error(f"Printer '{printer}' is not configured. Run setup_canon_printer.sh.")
            return False
        if "disabled" in status.stdout:
            logger.error(f"Printer '{printer}' is disabled: {status.stdout.strip()}")
            return False
        accepting = subprocess.run(["lpstat", "-a", printer], capture_output=True, text=True)
        if "not accepting" in accepting.stdout:
            logger.error(f"Printer '{printer}' is not accepting jobs: {accepting.stdout.strip()}")
            return False
        return True

    def lpr_command(self, file_path: Path, title: str) -> List[str]:
        cmd = ["lpr", "-P", self.config["printer_name"], "-T", title]
        for key, value in self.config["print_options"].items():
            if value is not None:
                cmd += ["-o", f"{key}={value}"]
        cmd.append(str(file_path))
        return cmd

    @staticmethod
    def to_print_jpeg(source: Path, dest: Path) -> None:
        """Write a print-ready JPEG: correct orientation, RGB, full resolution.

        CUPS can't reliably handle HEIC, and EXIF orientation is often ignored.
        """
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest, format="JPEG", quality=95)

    def print_photos(self, photos: List[Photo]) -> List[Photo]:
        """Send photos to the printer. Returns the ones successfully queued."""
        printer = self.config["printer_name"]
        if self.test_mode:
            logger.info(f"TEST MODE: would print {len(photos)} photos on {printer}:")
            for i, photo in enumerate(photos, 1):
                logger.info(f"  {i}. {photo.path}")
                logger.info(f"     {' '.join(self.lpr_command(Path('<converted>.jpg'), photo.path.name))}")
            return []

        if not self.printer_ready():
            logger.info(f"Nothing printed; selection metadata is in {self.metadata_dir}")
            return []

        queued: List[Photo] = []
        with tempfile.TemporaryDirectory(prefix="photo-print-") as tmp:
            for i, photo in enumerate(photos, 1):
                logger.info(f"Printing photo {i}/{len(photos)}: {photo.path.name}")
                try:
                    jpeg = Path(tmp) / f"{i:02d}_{photo.path.stem}.jpg"
                    self.to_print_jpeg(photo.path, jpeg)
                    result = subprocess.run(
                        self.lpr_command(jpeg, photo.path.name), capture_output=True, text=True
                    )
                except Exception as e:
                    logger.error(f"Error printing {photo.path}: {e}")
                    continue
                if result.returncode == 0:
                    logger.info(f"✓ Sent to printer: {photo.path.name}")
                    queued.append(photo)
                else:
                    logger.error(f"✗ Failed to print {photo.path}: {result.stderr.strip()}")
            # lpr copies the file into the spool before returning, so the temp
            # files can be removed once all jobs are submitted.

        logger.info(f"{len(queued)}/{len(photos)} print jobs submitted to {printer}")
        return queued

    # ----- main -------------------------------------------------------------

    def run(self) -> int:
        logger.info("Starting weekly photo selection and printing")
        try:
            self.model = self.ollama.pick_vision_model(self.config["vision_models"])
        except OllamaError as e:
            logger.error(str(e))
            return 1
        logger.info(f"Using vision model: {self.model}")

        photos = self.collect_weekly_photos()
        if not photos:
            logger.warning("No photos found for the past week")
            return 0

        selected, rated = self.select_top_photos(photos)
        if not selected:
            logger.warning("No photos selected")
            # Only a failure if photos needed rating and none could be rated.
            return 1 if self.attempted and not rated else 0

        self.save_selection_metadata(selected, found=len(photos), rated=rated)
        queued = self.print_photos(selected)
        if queued:
            self.record_printed(queued)

        logger.info("Weekly photo selection completed")
        return 0 if self.test_mode or len(queued) == len(selected) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly Photo Selector and Printer")
    parser.add_argument("--test", action="store_true", help="Select photos but don't print")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="Path to config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(Path(os.path.expanduser(config["log_dir"])))
    started = time.monotonic()
    code = PhotoSelector(config, test_mode=args.test).run()
    logger.info(f"Finished in {time.monotonic() - started:.0f}s (exit code {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
