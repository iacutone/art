"""
Where the weekly photos come from.

Each source returns the photos taken in [week_start, week_end) as local files,
so rating and printing work the same whichever source is used:

- SynologyPhotosSource scans the Synology Photos folders on the mounted NAS.
- AmazonPhotosSource downloads the week's photos from Amazon Photos into a
  working directory, using the same web API the Amazon Photos site uses.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests
from PIL import Image

from ollama_client import HEIF_SUPPORTED

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif"}

# EXIF tag ids
EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME_DIGITIZED = 36868
TAG_DATETIME = 306

logger = logging.getLogger("photo_selector")


class PhotoSourceError(Exception):
    pass


@dataclass
class Photo:
    path: Path  # local file used for rating and printing
    taken: datetime
    sha256: str = ""
    origin: str = ""  # where the photo lives: a NAS path or an Amazon Photos node
    rating: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.origin = self.origin or str(self.path)

    @property
    def score(self) -> int:
        return self.rating.get("score", 0)


def get_image_date(image_path: Path, fallback: Optional[datetime] = None) -> datetime:
    """Capture date from EXIF (DateTimeOriginal preferred), else `fallback`, else file mtime."""
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
    return fallback or datetime.fromtimestamp(image_path.stat().st_mtime)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def warn_if_no_heif() -> None:
    if not HEIF_SUPPORTED:
        logger.warning("pillow-heif not installed: HEIC photos will be skipped")


# ----- Synology Photos --------------------------------------------------------


class SynologyPhotosSource:
    """Scans Synology Photos folders on the NAS mounted locally (e.g. ~/nas-home)."""

    name = "Synology Photos"

    def __init__(self, photo_dirs: List[str]):
        self.photo_dirs = [Path(os.path.expanduser(d)) for d in photo_dirs]

    def collect(self, week_start: datetime, week_end: datetime, workdir: Path) -> List[Photo]:
        warn_if_no_heif()
        start_ts = week_start.timestamp()
        photos: List[Photo] = []
        seen_hashes = set()

        for photo_dir in self.photo_dirs:
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
                    taken = get_image_date(image_path)
                    if not (week_start <= taken < week_end):
                        continue
                    sha = file_hash(image_path)
                    if sha in seen_hashes:
                        logger.debug(f"Skipping duplicate {image_path}")
                        continue
                    seen_hashes.add(sha)
                    photos.append(Photo(image_path, taken, sha))
                except Exception as e:
                    logger.warning(f"Error processing {image_path}: {e}")
        return photos


# ----- Amazon Photos ----------------------------------------------------------

# Amazon has no public Amazon Photos API. This uses the endpoints behind the
# Amazon Photos website, authenticated with cookies copied from a signed-in
# browser, so it can break if Amazon changes the site or the cookies expire.
AMAZON_PAGE_SIZE = 200
AMAZON_MAX_OFFSET = 9999 - AMAZON_PAGE_SIZE  # Amazon rejects offset + limit > 9999
AMAZON_BASE_PARAMS = {"asset": "ALL", "tempLink": "false", "resourceVersion": "V2", "ContentType": "JSON"}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# EXIF capture times have no time zone, while Amazon's dates are UTC, so the
# candidate list is widened by this much before filtering on EXIF dates.
DATE_SLACK = timedelta(days=1)


def parse_amazon_date(value: Optional[str]) -> Optional[datetime]:
    """'2026-11-20T18:04:11.000Z' -> naive local datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return None


# Cookie region suffix -> Amazon domain, where they differ.
AMAZON_DOMAINS = {"uk": "co.uk", "jp": "co.jp", "au": "com.au", "br": "com.br", "mx": "com.mx"}


def amazon_tld(cookies: Dict[str, str]) -> str:
    """amazon.com uses *-main cookies; other regions use *-acb<region> (e.g. at-acbca -> ca, at-acbuk -> co.uk)."""
    for name in cookies:
        if name.endswith("-main"):
            return "com"
    for name in cookies:
        if name.startswith("at-acb"):
            region = name[len("at-acb"):]
            return AMAZON_DOMAINS.get(region, region)
    raise PhotoSourceError(
        "Amazon cookies need an 'at-main' cookie (amazon.com) or an 'at-acb<country>' cookie (other regions)"
    )


class AmazonPhotosSource:
    """Downloads the week's photos from Amazon Photos."""

    name = "Amazon Photos"

    def __init__(self, cookies_file: str, cookies: Optional[Dict[str, str]] = None):
        self.cookies_file = Path(os.path.expanduser(cookies_file))
        self.cookies = cookies
        self.session: Optional[requests.Session] = None
        self.drive_url = ""
        self.owner_id = ""

    @property
    def cookies_origin(self) -> str:
        return "the AMAZON_PHOTOS_* settings" if self.cookies else str(self.cookies_file)

    def load_cookies(self) -> Dict[str, str]:
        if self.cookies:
            return self.cookies
        if not self.cookies_file.exists():
            raise PhotoSourceError(
                f"No Amazon Photos sign-in: set AMAZON_PHOTOS_SESSION_ID, AMAZON_PHOTOS_UBID and "
                f"AMAZON_PHOTOS_AT (run ./setup_photo_selector.sh --configure), or create {self.cookies_file}. "
                "See 'Amazon Photos sign-in' in the README."
            )
        try:
            cookies = json.loads(self.cookies_file.read_text())
        except ValueError as e:
            raise PhotoSourceError(f"{self.cookies_file} is not valid JSON: {e}")
        if not isinstance(cookies, dict) or "session-id" not in cookies:
            raise PhotoSourceError(f"{self.cookies_file} must be a JSON object with a 'session-id' cookie")
        return cookies

    def connect(self) -> None:
        cookies = self.load_cookies()

        tld = amazon_tld(cookies)
        self.drive_url = f"https://www.amazon.{tld}/drive/v1"
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update({"user-agent": USER_AGENT, "x-amzn-sessionid": cookies["session-id"]})

        root = self.get_json("/nodes", {"filters": "isRoot:true"})
        try:
            self.owner_id = root["data"][0]["ownerId"]
        except (KeyError, IndexError, TypeError):
            raise PhotoSourceError(f"Unexpected reply when looking up the Amazon Photos library: {root}")

    def get_json(self, path: str, params: Dict) -> Dict:
        try:
            r = self.session.get(self.drive_url + path, params={**AMAZON_BASE_PARAMS, **params}, timeout=60)
        except requests.RequestException as e:
            raise PhotoSourceError(f"Could not reach Amazon Photos: {e}")
        if r.status_code in (401, 403):
            raise PhotoSourceError(
                f"Amazon Photos rejected the sign-in cookies (HTTP {r.status_code}). "
                f"They have probably expired; copy fresh ones into {self.cookies_origin}."
            )
        if not r.ok:
            raise PhotoSourceError(f"Amazon Photos request failed (HTTP {r.status_code}): {r.text[:300]}")
        return r.json()

    def recent_nodes(self, since: datetime) -> Iterator[Dict]:
        """Photo nodes uploaded at or after `since`, newest upload first.

        A photo can't have been uploaded before it was taken, so paging by
        upload date stops as soon as uploads are older than the week.
        """
        offset = 0
        while offset <= AMAZON_MAX_OFFSET:
            page = self.get_json("/search", {
                "filters": "type:(PHOTOS)",
                "sort": "['createdDate DESC']",
                "limit": AMAZON_PAGE_SIZE,
                "offset": offset,
                "searchContext": "customer",
                "lowResThumbnail": "true",
            })
            nodes = page.get("data") or []
            for node in nodes:
                created = parse_amazon_date(node.get("createdDate"))
                if created and created < since:
                    return
                yield node
            if len(nodes) < AMAZON_PAGE_SIZE:
                return
            offset += AMAZON_PAGE_SIZE
        logger.warning("Reached Amazon's search limit of 10,000 photos; older uploads were not checked")

    def download(self, node: Dict, dest_dir: Path) -> Path:
        dest = dest_dir / f"{node['id']}_{Path(node.get('name') or 'photo.jpg').name}"
        url = f"{self.drive_url}/nodes/{node['id']}/contentRedirection"
        params = {"querySuffix": "?download=true", "ownerId": self.owner_id}
        with self.session.get(url, params=params, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
        return dest

    def collect(self, week_start: datetime, week_end: datetime, workdir: Path) -> List[Photo]:
        warn_if_no_heif()
        self.connect()
        logger.info(f"Searching Amazon Photos ({self.drive_url})")

        candidates = []
        for node in self.recent_nodes(since=week_start - DATE_SLACK):
            name = node.get("name") or ""
            if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            content_date = parse_amazon_date((node.get("contentProperties") or {}).get("contentDate"))
            # contentDate is Amazon's capture date; filter roughly on it here
            # and exactly on EXIF after downloading.
            if content_date and not (week_start - DATE_SLACK <= content_date < week_end + DATE_SLACK):
                continue
            candidates.append((node, content_date))
        logger.info(f"Downloading {len(candidates)} candidate photos from Amazon Photos")

        dest_dir = workdir / "amazon"
        dest_dir.mkdir(parents=True, exist_ok=True)
        photos: List[Photo] = []
        seen_hashes = set()
        for node, content_date in candidates:
            name = node.get("name") or node["id"]
            try:
                path = self.download(node, dest_dir)
                taken = get_image_date(path, fallback=content_date)
                if not (week_start <= taken < week_end):
                    path.unlink()
                    continue
                sha = file_hash(path)
                if sha in seen_hashes:
                    logger.debug(f"Skipping duplicate {name}")
                    path.unlink()
                    continue
                seen_hashes.add(sha)
                photos.append(Photo(path, taken, sha, origin=f"amazon-photos:{node['id']}/{name}"))
            except Exception as e:
                logger.warning(f"Error downloading {name} from Amazon Photos: {e}")
        return photos


SOURCES = ("synology", "amazon")


def make_source(config: dict):
    source = config["photo_source"]
    if source == "amazon":
        amazon = config["amazon_photos"]
        return AmazonPhotosSource(amazon["cookies_file"], amazon.get("cookies"))
    if source == "synology":
        return SynologyPhotosSource(config["photo_dirs"])
    raise ValueError(f"photo_source must be one of {', '.join(SOURCES)}, not {source!r}")
