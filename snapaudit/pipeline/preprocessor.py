"""
Prepare validated image inputs for the vision model.

Loads each image (URL or embedded base64), normalizes colour space, resizes
according to ``config.yaml``, and emits JPEG bytes. Callers can encode those
bytes with :func:`to_base64` or :func:`to_base64_strings` for the Ollama API.
"""

from __future__ import annotations

import base64
import binascii
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

import httpx
import yaml
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PreprocessingError(Exception):
    """Raised when a single slot in an image set cannot be decoded or resized."""

    def __init__(self, image_index: int, message: str) -> None:
        self.image_index = image_index
        self.message = message
        super().__init__(f"[{image_index}] {message}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _config_path() -> Path:
    """Resolve repo-root ``config.yaml`` next to the ``snapaudit`` package."""
    return Path(__file__).resolve().parents[2] / "config.yaml"


def _load_config_values() -> dict[str, Any]:
    """Read ``config.yaml`` (PyYAML)."""
    path = _config_path()
    with path.open("rb") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config at {path} must parse to a mapping")
    return data


def _image_resize_px() -> int:
    """Square edge length for model input (``image_resize`` in config, default 448)."""
    cfg = _load_config_values()
    return int(cfg.get("image_resize", 448))


# ---------------------------------------------------------------------------
# Loading raw bytes from a string (URL, data URL, or bare base64)
# ---------------------------------------------------------------------------

_DATA_URL_BROAD: Final[re.Pattern[str]] = re.compile(
    r"^data:(image/[^;]+);base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _decode_base64_data(data_b64: str) -> bytes:
    """Decode URL-safe or standard base64; raises on invalid input."""
    cleaned = re.sub(r"\s+", "", data_b64)
    pad = (-len(cleaned)) % 4
    cleaned += "=" * pad
    if "-" in cleaned or "_" in cleaned:
        return base64.urlsafe_b64decode(cleaned)
    return base64.b64decode(cleaned, validate=True)


def _fetch_url_bytes(url: str) -> bytes:
    """Download image bytes over HTTP(S)."""
    headers = {"User-Agent": "SnapAudit-Preprocessor/1.0"}
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _raw_bytes_from_input(image_data: str) -> bytes:
    """
    Turn a validator-shaped string into raw image bytes.

    Supports ``data:image/...;base64,...``, ``http(s)`` URLs, and bare base64
    payloads (decoded then passed to Pillow).
    """
    raw = image_data.strip()
    if not raw:
        raise ValueError("empty image string")

    # Embedded base64 in a data URL
    if raw.startswith("data:"):
        m = _DATA_URL_BROAD.match(raw)
        if not m:
            raise ValueError("malformed data URL")
        try:
            return base64.b64decode(m.group(2), validate=True)
        except binascii.Error as exc:
            raise ValueError("invalid base64 in data URL") from exc

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        return _fetch_url_bytes(raw)

    # Bare base64 (no ``data:`` prefix), as accepted by the validator
    try:
        return _decode_base64_data(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("not a valid URL or base64 image payload") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preprocess_image(image_data: str) -> bytes:
    """
    Load one image string, normalize it for the vision model, return JPEG bytes.

    Steps:

    1. Resolve **raw bytes** — download if ``http(s)``, decode if data URL or
       bare base64 (same shapes as :mod:`snapaudit.pipeline.validator`).
    2. **Open** with Pillow and fully load the raster (catches truncated files).
    3. **Auto-orient** using EXIF so width/height match what a human sees.
    4. **Convert to RGB** — greyscale, RGBA, CMYK, P, etc. become 8-bit RGB.
    5. **Resize** to ``image_resize`` × ``image_resize`` from ``config.yaml``
       (default 448) using high-quality resampling.
    6. **Encode** as JPEG and return the byte string.
    """
    payload = _raw_bytes_from_input(image_data)

    try:
        with Image.open(BytesIO(payload)) as img:
            img.load()
            # Correct for camera rotation before we resize or flatten colour.
            img = ImageOps.exif_transpose(img)
            rgb = img.convert("RGB")
    except OSError as exc:
        raise ValueError(f"cannot open or read image: {exc}") from exc

    edge = _image_resize_px()
    resized = rgb.resize((edge, edge), Image.Resampling.LANCZOS)

    out = BytesIO()
    resized.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def preprocess_set(image_set: list[str]) -> list[bytes]:
    """
    Run :func:`preprocess_image` on each entry.

    On the first failure (corrupt payload, decode error, Pillow error), raises
    :class:`PreprocessingError` with the failing **index** in ``image_set``.
    """
    result: list[bytes] = []
    for index, item in enumerate(image_set):
        try:
            result.append(preprocess_image(item))
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise PreprocessingError(index, str(exc)) from exc
    return result


def to_base64(image_bytes: bytes) -> str:
    """
    Encode processed JPEG **bytes** as a standard base64 **string** (no
    ``data:`` prefix) for JSON bodies to Ollama or other APIs.
    """
    return base64.b64encode(image_bytes).decode("ascii")


def to_base64_strings(processed_images: list[bytes]) -> list[str]:
    """
    Encode each processed image with :func:`to_base64`.

    Use this after :func:`preprocess_set` when building the model request
    payload (e.g. multiple base64 image fields for Ollama).
    """
    return [to_base64(blob) for blob in processed_images]


def preprocess_set_to_base64_strings(image_set: list[str]) -> list[str]:
    """
    Convenience: :func:`preprocess_set` then :func:`to_base64_strings`.

    Returns base64-encoded JPEG strings ready for Ollama-style multimodal
    requests in one call.
    """
    return to_base64_strings(preprocess_set(image_set))
