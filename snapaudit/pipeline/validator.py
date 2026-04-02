"""
Validate inbound audit API payloads before image work or model inference.

Rules run in a fixed order; the first failure short-circuits and returns a
`ValidationError`. Successful validation returns ``None``.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

import httpx
import yaml

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Machine-readable location plus a human-facing message for API clients."""

    field: str
    message: str


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _config_path() -> Path:
    """Resolve repo-root ``config.yaml`` next to the ``snapaudit`` package."""
    return Path(__file__).resolve().parents[2] / "config.yaml"


def _load_config_values() -> dict[str, Any]:
    """Read limits from ``config.yaml`` (PyYAML)."""
    path = _config_path()
    with path.open("rb") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config at {path} must parse to a mapping")
    return data


def _config_limits() -> tuple[int, int, float]:
    """Return ``(min_images, max_images, max_file_size_mb)`` with safe defaults."""
    cfg = _load_config_values()
    min_n = int(cfg.get("min_images_per_set", 2))
    max_n = int(cfg.get("max_images_per_set", 3))
    max_mb = float(cfg.get("max_file_size_mb", 10))
    return min_n, max_n, max_mb


# ---------------------------------------------------------------------------
# Comparison & media helpers
# ---------------------------------------------------------------------------

_ALLOWED_COMPARISON_TYPES: Final[frozenset[str]] = frozenset(
    {"catalog_vs_icud", "catalog_vs_pickup"}
)

# URL path extensions → canonical label used in error messages
_EXT_TO_LABEL: Final[dict[str, str]] = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

_CONTENT_TYPE_TO_LABEL: Final[dict[str, str]] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

# Any image/* data URL — used so unsupported mimes (e.g. GIF) fail with a clear label
_DATA_URL_BROAD: Final[re.Pattern[str]] = re.compile(
    r"^data:(image/[^;]+);base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _bytes_format_label(head: bytes) -> str | None:
    """Infer JPEG / PNG / WEBP from magic bytes."""
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return None


def _mime_tail(mime: str) -> str:
    """Return a short uppercase token for errors (e.g. ``image/gif`` → ``GIF``)."""
    return (mime.split("/", 1)[-1] if "/" in mime else mime).upper()


def _decode_base64_data(data_b64: str) -> bytes:
    """Decode URL-safe or standard base64; raises on invalid input."""
    cleaned = re.sub(r"\s+", "", data_b64)
    pad = (-len(cleaned)) % 4
    cleaned += "=" * pad
    if "-" in cleaned or "_" in cleaned:
        return base64.urlsafe_b64decode(cleaned)
    return base64.b64decode(cleaned, validate=True)


def _http_url_format_decision(url: str) -> tuple[bytes, str]:
    """
    Validate ``http``/``https`` URLs by path suffix only (no network I/O).

    - Path ends with ``.jpg`` / ``.jpeg`` / ``.png`` / ``.webp`` → accept.
    - Path has another non-empty extension (e.g. ``.gif``, ``.pdf``) → reject.
    - No file extension on the last path segment → accept (preprocessor loads bytes).
    """
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if not path:
        return b"", "JPEG"
    ext = Path(path).suffix.lower()
    if ext in _EXT_TO_LABEL:
        return b"", _EXT_TO_LABEL[ext]
    if ext:
        token = ext.lstrip(".").upper()
        raise ValueError(f"unsupported format {token}")
    return b"", "JPEG"


def _image_bytes_and_format(item: str) -> tuple[bytes, str]:
    """
    Return raw image bytes and a format label (JPEG, PNG, WEBP).

    ``item`` may be a data URL, a remote URL, or raw/base64 without a data:
    prefix (magic-byte sniffing).

    For ``http``/``https``, only the URL path suffix is checked here; URLs with no
    image extension are accepted and validated when bytes are loaded later.

    For ``data:image/...;base64,...``, the declared MIME must be JPEG, PNG, or WEBP.
    """
    raw = item.strip()
    if not raw:
        raise ValueError("empty image entry")

    # data:image/...;base64,... — strict MIME allowlist (e.g. GIF rejected)
    if raw.startswith("data:"):
        m = _DATA_URL_BROAD.match(raw)
        if not m:
            raise ValueError("malformed data URL")
        mime = m.group(1).strip().lower()
        label = _CONTENT_TYPE_TO_LABEL.get(mime)
        if label is None:
            raise ValueError(f"unsupported format {_mime_tail(mime)}")
        try:
            payload = base64.b64decode(m.group(2), validate=True)
        except binascii.Error as exc:
            raise ValueError("invalid base64 in data URL") from exc
        return payload, label

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        return _http_url_format_decision(raw)

    try:
        payload = _decode_base64_data(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("not a valid URL or base64 image payload") from exc
    label = _bytes_format_label(payload[:16])
    if label is None:
        raise ValueError("unsupported format UNKNOWN")
    return payload, label


def _url_content_length(url: str, max_file_bytes: int) -> int:
    """Return byte size for a remote asset using Content-Length or a bounded GET."""
    headers = {"User-Agent": "SnapAudit-Validator/1.0"}
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        head = client.head(url)
        head.raise_for_status()
        cl = head.headers.get("content-length")
        if cl is not None and cl.isdigit():
            return int(cl)
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > max_file_bytes:
                    return total
            return total


def _size_mb_from_entry(item: str, max_file_bytes: int) -> float:
    """Compute payload size in MB for validation rule 6."""
    raw = item.strip()
    if not raw:
        return 0.0

    if raw.startswith("data:"):
        m = _DATA_URL_BROAD.match(raw)
        if not m:
            return 0.0
        try:
            payload = base64.b64decode(m.group(2), validate=True)
        except binascii.Error:
            return 0.0
        return len(payload) / (1024.0 * 1024.0)

    parsed = urlparse(raw.strip())
    if parsed.scheme in {"http", "https"}:
        return _url_content_length(raw.strip(), max_file_bytes) / (1024.0 * 1024.0)

    payload = _decode_base64_data(raw)
    return len(payload) / (1024.0 * 1024.0)


def validate_request(
    *,
    session_id: Any,
    comparison_type: Any,
    image_set_1: Any,
    image_set_2: Any,
) -> ValidationError | None:
    """
    Run all validation rules in order.

    Returns ``None`` when the payload is acceptable; otherwise a single
    ``ValidationError`` describing the first failed rule.
    """
    min_n, max_n, max_mb = _config_limits()
    max_bytes = int(max_mb * 1024 * 1024)

    # Rule 1 — ``session_id`` must be supplied (never auto-generated server-side).
    if session_id is None or (isinstance(session_id, str) and not session_id.strip()):
        return ValidationError(
            field="session_id",
            message="session_id is required. The system does not auto-generate one.",
        )

    # Rule 2 — ``comparison_type`` is a closed set of business comparison modes.
    ct = comparison_type if isinstance(comparison_type, str) else None
    if ct is None or ct not in _ALLOWED_COMPARISON_TYPES:
        return ValidationError(
            field="comparison_type",
            message="comparison_type must be one of: catalog_vs_icud, catalog_vs_pickup",
        )

    set1 = image_set_1 if isinstance(image_set_1, list) else None
    set2 = image_set_2 if isinstance(image_set_2, list) else None

    # Rule 3 — first image group must contain between ``min_images_per_set`` and
    # ``max_images_per_set`` entries (defaults 2–3 from config).
    if set1 is None:
        return ValidationError(
            field="image_set_1",
            message=(
                f"image_set_1 contains 0 images; minimum is {min_n}, maximum is {max_n}"
            ),
        )
    n1 = len(set1)
    if n1 < min_n or n1 > max_n:
        return ValidationError(
            field="image_set_1",
            message=(
                f"image_set_1 contains {n1} images; minimum is {min_n}, maximum is {max_n}"
            ),
        )

    # Rule 4 — same bounds as rule 3 for the second image group.
    if set2 is None:
        return ValidationError(
            field="image_set_2",
            message=(
                f"image_set_2 contains 0 images; minimum is {min_n}, maximum is {max_n}"
            ),
        )
    n2 = len(set2)
    if n2 < min_n or n2 > max_n:
        return ValidationError(
            field="image_set_2",
            message=(
                f"image_set_2 contains {n2} images; minimum is {min_n}, maximum is {max_n}"
            ),
        )

    # Rule 5 — each slot must be JPEG, PNG, or WEBP (data URL mime, URL suffix /
    # Content-Type, or magic bytes for raw base64).
    for set_name, items in (("image_set_1", set1), ("image_set_2", set2)):
        for i, entry in enumerate(items):
            if not isinstance(entry, str):
                return ValidationError(
                    field=f"{set_name}[{i}]",
                    message="each image must be a string (URL or base64 payload)",
                )
            try:
                _image_bytes_and_format(entry)
            except ValueError as exc:
                err = str(exc)
                # Wrong media type / unreadable kind of image → fixed template.
                if err.startswith("unsupported format "):
                    fmt_token = err.removeprefix("unsupported format ").strip()
                    msg = (
                        f"{set_name}[{i}] has unsupported format {fmt_token}; "
                        "accepted: JPEG, PNG, WEBP"
                    )
                else:
                    # Malformed payloads (bad base64, empty slot, etc.) — surface the cause.
                    msg = f"{set_name}[{i}]: {err}"
                return ValidationError(field=set_name, message=msg)

    # Rule 6 — decoded payload (or remote Content-Length / streamed GET) must not
    # exceed ``max_file_size_mb`` from config.
    for set_name, items in (("image_set_1", set1), ("image_set_2", set2)):
        for i, entry in enumerate(items):
            assert isinstance(entry, str)
            try:
                size_mb = _size_mb_from_entry(entry, max_bytes)
            except (httpx.HTTPError, ValueError, binascii.Error) as exc:
                return ValidationError(
                    field=f"{set_name}[{i}]",
                    message=f"could not read image size: {exc}",
                )
            if size_mb > max_mb:
                return ValidationError(
                    field=set_name,
                    message=(
                        f"{set_name}[{i}] is {size_mb:.2f}MB; maximum file size is {int(max_mb)}MB"
                    ),
                )

    return None
