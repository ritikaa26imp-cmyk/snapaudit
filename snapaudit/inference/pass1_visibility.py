"""
Pass 1 — per-image visibility only (no attribute comparison).

Images are flattened as **set 1 first, then set 2** when sent to Ollama so the
multimodal API receives one ``images`` array; the system prompt states that
ordering explicitly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Final

from snapaudit.inference.model import JSONParseError, OllamaClient, parse_json_response
from snapaudit.inference.prompt_builder import build_pass1_prompt
from snapaudit.pipeline.preprocessor import preprocess_set_to_base64_strings

_VISIBILITY: Final[frozenset[str]] = frozenset(
    {"visible", "partial", "not_visible"},
)


@dataclass(slots=True)
class Pass1Result:
    """Structured Pass 1 output plus timing and the raw model string."""

    set_1_visibility: list[dict[str, Any]]
    set_2_visibility: list[dict[str, Any]]
    latency_ms: int
    raw_response: str


def _ordering_hint(n_set1: int, n_set2: int) -> str:
    """Explain how flattened images map back to set_1 / set_2 in the JSON."""
    total = n_set1 + n_set2
    return (
        f"\n\nImage ordering for this request: {total} raster(s) are attached in one batch. "
        f"The first {n_set1} image(s) are from **image set 1** (label image_index 1..{n_set1} "
        f"within that set). The following {n_set2} image(s) are from **image set 2** "
        f"(label image_index 1..{n_set2} within that set). "
        f"Return exactly {n_set1} objects in set_1_visibility and {n_set2} in set_2_visibility."
    )


def parse_pass1_response(response: str) -> dict[str, Any]:
    """
    Parse Pass 1 JSON and validate the visibility schema.

    Raises :class:`JSONParseError` if JSON is invalid or keys / values do not match
    the Pass 1 contract.
    """
    data = parse_json_response(response)

    s1 = data.get("set_1_visibility")
    s2 = data.get("set_2_visibility")
    if not isinstance(s1, list) or not isinstance(s2, list):
        raise JSONParseError(response)

    data["set_1_visibility"] = _normalize_visibility_list(s1, response)
    data["set_2_visibility"] = _normalize_visibility_list(s2, response)
    return data


def _normalize_visibility_list(items: list[Any], raw_response: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise JSONParseError(raw_response)
        idx = item.get("image_index")
        vis = item.get("visibility")
        if idx is None or vis is None:
            raise JSONParseError(raw_response)
        try:
            idx_int = int(idx)
        except (TypeError, ValueError):
            raise JSONParseError(raw_response) from None
        vis_s = str(vis).strip().lower()
        if vis_s not in _VISIBILITY:
            raise JSONParseError(raw_response)
        out.append({"image_index": idx_int, "visibility": vis_s})
    return out


async def run_pass1(
    image_set_1: list[str],
    image_set_2: list[str],
    *,
    preprocessed_b64: list[str] | None = None,
) -> Pass1Result:
    """
    Preprocess images, run the visibility system prompt on Ollama, parse JSON.

    If ``preprocessed_b64`` is supplied (JPEGs already base64-encoded in set-1-then-set-2
    order), preprocessing is skipped—callers that already ran :func:`preprocess_set`
    should pass it to avoid duplicate work.

    Latency is end-to-end wall time for preprocessing + one chat round-trip +
    parsing (milliseconds).
    """
    n1, n2 = len(image_set_1), len(image_set_2)
    started = time.perf_counter()

    # One multimodal batch: set 1 images first, then set 2 (see `_ordering_hint`).
    if preprocessed_b64 is not None:
        if len(preprocessed_b64) != n1 + n2:
            raise ValueError(
                "preprocessed_b64 length must equal len(image_set_1) + len(image_set_2)"
            )
        b64_images = preprocessed_b64
    else:
        b64_images = preprocess_set_to_base64_strings(image_set_1 + image_set_2)

    system_prompt = build_pass1_prompt() + _ordering_hint(n1, n2)
    client = OllamaClient()
    raw = await client.chat(system_prompt, b64_images)

    parsed = parse_pass1_response(raw)
    latency_ms = int((time.perf_counter() - started) * 1000)

    return Pass1Result(
        set_1_visibility=parsed["set_1_visibility"],
        set_2_visibility=parsed["set_2_visibility"],
        latency_ms=latency_ms,
        raw_response=raw,
    )
