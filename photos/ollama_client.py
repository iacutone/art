"""Small Ollama client shared by the photo selector and its test script."""

import base64
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

import requests
from PIL import Image, ImageOps

try:  # HEIC/HEIF support (iPhone photos)
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - depends on environment
    HEIF_SUPPORTED = False

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an unusable response."""


def encode_image_base64(image: Union[Path, Image.Image], max_size: int = 1024) -> str:
    """Return a JPEG-encoded, base64 string of the image, downscaled to max_size."""
    if isinstance(image, Image.Image):
        img = image.copy()
    else:
        with Image.open(image) as opened:
            img = ImageOps.exif_transpose(opened)
            img.load()
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _base_name(model: str) -> str:
    return model.split(":", 1)[0] if model.endswith(":latest") else model


class OllamaClient:
    def __init__(self, url: str = DEFAULT_OLLAMA_URL):
        self.url = url.rstrip("/")

    def list_models(self) -> List[str]:
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise OllamaError(f"Cannot reach Ollama at {self.url}: {e}") from e
        return [m["name"] for m in response.json().get("models", [])]

    def supports_vision(self, model: str) -> Optional[bool]:
        """True/False if Ollama reports model capabilities, None if it doesn't say."""
        try:
            response = requests.post(f"{self.url}/api/show", json={"model": model}, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            return None
        capabilities = response.json().get("capabilities")
        if capabilities is None:
            return None
        return "vision" in capabilities

    def pick_vision_model(self, preferred: List[str]) -> str:
        """Return the first installed model from `preferred` that can see images.

        Never falls back to an arbitrary model: a text-only model would invent
        scores for images it cannot see.
        """
        installed = self.list_models()
        installed_by_base = {_base_name(m): m for m in installed}
        for wanted in preferred:
            actual = installed_by_base.get(_base_name(wanted))
            if actual is None:
                continue
            if self.supports_vision(actual) is False:
                logger.warning(f"Model {actual} is installed but has no vision capability; skipping")
                continue
            return actual
        raise OllamaError(
            f"None of the vision models {preferred} are installed (installed: {installed or 'none'}). "
            f"Install one with: ollama pull {preferred[0]}"
        )

    def generate_json(self, model: str, prompt: str, image_b64: str, timeout: int = 180) -> dict:
        """Ask the model about an image and return its JSON reply as a dict."""
        try:
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "format": "json",
                },
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise OllamaError(f"Ollama request failed: {e}") from e

        text = response.json().get("response", "")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise OllamaError(f"Model returned invalid JSON: {text[:200]!r}") from e
        if not isinstance(parsed, dict):
            raise OllamaError(f"Model returned JSON that is not an object: {text[:200]!r}")
        return parsed
