"""
Pass 2 — full attribute comparison and verdict.

Images are sent in the same **set 1 then set 2** order as Pass 1. If the model
returns JSON that fails validation, we retry **once** with the same prompt and
record that in :attr:`Pass2Result.json_retried` for downstream confidence logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from snapaudit.inference.model import JSONParseError, OllamaClient, parse_json_response
from snapaudit.inference.prompt_builder import build_pass2_prompt
from snapaudit.pipeline.preprocessor import preprocess_set_to_base64_strings

_CATEGORY: frozenset[str] = frozenset(
    {"saree", "kurti", "bag", "cloth", "jewellery", "watch", "unknown"},
)
_TRIPLES: frozenset[str] = frozenset({"same", "different", "cant_say"})
_VISIBILITY: frozenset[str] = frozenset({"visible", "partial", "not_visible"})
_VERDICT: frozenset[str] = frozenset({"match", "mismatch", "inconclusive"})

_PASS2_KEYS: tuple[str, ...] = (
    "category_detected",
    "colour",
    "design",
    "category_match",
    "quantity",
    "is_product_visible_set1",
    "is_product_visible_set2",
    "verdict",
    "description",
)


@dataclass(slots=True)
class Pass2Result:
    """Structured Pass 2 output, timing, retry flag, and raw model text."""

    category_detected: str
    colour: str
    design: str
    category_match: str
    quantity: str
    is_product_visible_set1: str
    is_product_visible_set2: str
    verdict: str
    description: str
    latency_ms: int
    json_retried: bool
    raw_response: str


def _ordering_hint(n_set1: int, n_set2: int) -> str:
    total = n_set1 + n_set2
    return (
        f"\n\nImage ordering for this request: {total} raster(s) are attached in one batch. "
        f"The first {n_set1} image(s) belong to **image set 1**; the next {n_set2} belong to "
        f"**image set 2**. Judge each set as a group of complementary views."
    )


def parse_pass2_response(response: str) -> dict[str, str]:
    """
    Parse Pass 2 JSON and validate required keys and allowed enum tokens.

    String fields are normalized to lowercase. Raises :class:`JSONParseError`
    on any mismatch.
    """
    data = parse_json_response(response)

    for key in _PASS2_KEYS:
        if key not in data:
            raise JSONParseError(response)
        val = data[key]
        if not isinstance(val, str):
            raise JSONParseError(response)

    cat = data["category_detected"].strip().lower()
    if cat not in _CATEGORY:
        raise JSONParseError(response)

    out: dict[str, str] = {"category_detected": cat}

    for key in ("colour", "design", "category_match", "quantity"):
        v = data[key].strip().lower()
        if v not in _TRIPLES:
            raise JSONParseError(response)
        out[key] = v

    for key in ("is_product_visible_set1", "is_product_visible_set2"):
        v = data[key].strip().lower()
        if v not in _VISIBILITY:
            raise JSONParseError(response)
        out[key] = v

    verdict = data["verdict"].strip().lower()
    if verdict not in _VERDICT:
        raise JSONParseError(response)
    out["verdict"] = verdict

    out["description"] = data["description"].strip()
    return out


def count_cant_say(result: Pass2Result) -> int:
    """Count how many of the four comparison attributes are ``cant_say``."""
    n = 0
    for field in (result.colour, result.design, result.category_match, result.quantity):
        if field == "cant_say":
            n += 1
    return n


def _to_pass2_result(
    parsed: dict[str, str],
    latency_ms: int,
    json_retried: bool,
    raw_response: str,
) -> Pass2Result:
    return Pass2Result(
        category_detected=parsed["category_detected"],
        colour=parsed["colour"],
        design=parsed["design"],
        category_match=parsed["category_match"],
        quantity=parsed["quantity"],
        is_product_visible_set1=parsed["is_product_visible_set1"],
        is_product_visible_set2=parsed["is_product_visible_set2"],
        verdict=parsed["verdict"],
        description=parsed["description"],
        latency_ms=latency_ms,
        json_retried=json_retried,
        raw_response=raw_response,
    )


async def run_pass2(
    image_set_1: list[str],
    image_set_2: list[str],
    comparison_type: str,
    category: str,
    visibility_context: str,
    user_prompt: str,
    *,
    preprocessed_b64: list[str] | None = None,
) -> Pass2Result:
    """
    Preprocess images, run Pass 2 prompt on Ollama, parse and validate JSON.

    On the first **invalid** structured response, issues **one** identical retry
    (same prompt and images) and sets ``json_retried=True`` if that retry is used.

    If ``preprocessed_b64`` is provided (set-1-then-set-2 order), decoding/downloading
    is skipped.

    ``latency_ms`` covers preprocessing plus **all** chat attempts.
    """
    n1, n2 = len(image_set_1), len(image_set_2)
    started = time.perf_counter()

    if preprocessed_b64 is not None:
        if len(preprocessed_b64) != n1 + n2:
            raise ValueError(
                "preprocessed_b64 length must equal len(image_set_1) + len(image_set_2)"
            )
        b64_images = preprocessed_b64
    else:
        b64_images = preprocess_set_to_base64_strings(image_set_1 + image_set_2)
    system_prompt = (
        build_pass2_prompt(comparison_type, category, visibility_context, user_prompt)
        + _ordering_hint(n1, n2)
    )

    client = OllamaClient()
    json_retried = False

    raw = await client.chat(system_prompt, b64_images)
    try:
        parsed = parse_pass2_response(raw)
    except JSONParseError:
        json_retried = True
        raw = await client.chat(system_prompt, b64_images)
        parsed = parse_pass2_response(raw)

    latency_ms = int((time.perf_counter() - started) * 1000)
    return _to_pass2_result(parsed, latency_ms, json_retried, raw)
