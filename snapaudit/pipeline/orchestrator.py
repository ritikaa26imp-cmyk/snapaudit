"""
End-to-end comparison pipeline.

Steps are deliberately **strictly ordered**: validate before spendy I/O, preprocess
before model calls, visibility before attribute comparison (rollup gate), then
deterministic confidence from signals—not model self-report. Persistence runs
last so clients always see an ``audit_id`` only after a durable row exists (for
successful paths).
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Final

from snapaudit.audit.log import AuditRecord, save_audit
from snapaudit.inference.model import get_active_model
from snapaudit.inference.pass1_visibility import Pass1Result, run_pass1
from snapaudit.inference.pass2_compare import Pass2Result, count_cant_say, run_pass2
from snapaudit.pipeline.confidence import ConfidenceSignals, compute_confidence
from snapaudit.pipeline.preprocessor import (
    PreprocessingError,
    preprocess_set,
    to_base64_strings,
)
from snapaudit.pipeline.rollup import rollup_both_sets
from snapaudit.pipeline.validator import ValidationError, validate_request

# ---------------------------------------------------------------------------
# Request / response + validation wrapper
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ComparisonRequest:
    """Inbound comparison job (matches the HTTP contract)."""

    session_id: str
    comparison_type: str
    image_set_1: list[str]
    image_set_2: list[str]
    category_hint: str = "auto"
    user_prompt: str = ""


@dataclass(slots=True)
class ComparisonResponse:
    """Outbound result for one comparison (PRD-shaped payload for APIs)."""

    session_id: str
    comparison_type: str
    category_hint: str
    user_prompt: str
    verdict: str | None
    confidence: str | None
    category_detected: str | None
    colour: str | None
    design: str | None
    category_match: str | None
    quantity: str | None
    is_product_visible_set1: str | None
    is_product_visible_set2: str | None
    description: str | None
    model_used: str | None
    pass1_latency_ms: int | None
    pass2_latency_ms: int | None
    total_latency_ms: int | None
    json_retried: bool
    short_circuited: bool
    short_circuit_reason: str | None
    audit_id: str | None
    overwritten: bool
    error: str | None
    status_code: int


class ComparisonValidationError(Exception):
    """Raised when :func:`validate_request` fails (map to HTTP 4xx in the API layer)."""

    def __init__(self, detail: ValidationError) -> None:
        self.detail = detail
        super().__init__(detail.message)


# Tiny valid JPEG as data URL — pads Pass 1 to two images on the dummy side for
# ``run_visibility_check`` without pulling network assets.
_MINI_JPEG_DATA_URL: Final[str] = (
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/"
    "wAARCAABAAEDAREAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/"
    "8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="
)


def _visibility_strings(rows: list[dict[str, Any]]) -> list[str]:
    """Stable ordering by ``image_index`` → plain labels for :func:`rollup_both_sets`."""
    ordered = sorted(rows, key=lambda r: int(r["image_index"]))
    return [str(r["visibility"]).strip().lower() for r in ordered]


def _visibility_context_blob(pass1: Pass1Result) -> str:
    """Structured Pass 1 facts injected into the Pass 2 system prompt."""
    return json.dumps(
        {
            "set_1_visibility": pass1.set_1_visibility,
            "set_2_visibility": pass1.set_2_visibility,
        },
        indent=2,
    )


def _new_audit_id() -> str:
    return f"AUD-{secrets.randbelow(100_000):05d}"


def _category_hint_provided(hint: str) -> bool:
    return hint.strip().lower() not in {"", "auto"}


async def run_comparison(request: ComparisonRequest) -> ComparisonResponse:
    """
    Execute validation → preprocess → Pass 1 → rollup gate → Pass 2 → confidence
    → audit row → response.
    """
    t_all = time.perf_counter()

    # STEP 1 — reject bad payloads before any download or GPU work.
    v = validate_request(
        session_id=request.session_id,
        comparison_type=request.comparison_type,
        image_set_1=request.image_set_1,
        image_set_2=request.image_set_2,
    )
    if v is not None:
        raise ComparisonValidationError(v)

    model_used = get_active_model()

    # STEP 2 — normalize pixels once; attribute-specific prompts reuse these tensors.
    try:
        bytes_1 = preprocess_set(request.image_set_1)
    except PreprocessingError as exc:
        return ComparisonResponse(
            session_id=request.session_id,
            comparison_type=request.comparison_type,
            category_hint=request.category_hint,
            user_prompt=request.user_prompt,
            verdict=None,
            confidence=None,
            category_detected=None,
            colour=None,
            design=None,
            category_match=None,
            quantity=None,
            is_product_visible_set1=None,
            is_product_visible_set2=None,
            description=None,
            model_used=model_used,
            pass1_latency_ms=None,
            pass2_latency_ms=None,
            total_latency_ms=int((time.perf_counter() - t_all) * 1000),
            json_retried=False,
            short_circuited=False,
            short_circuit_reason=None,
            audit_id=None,
            overwritten=False,
            error=f"image_set_1[{exc.image_index}]: {exc.message}",
            status_code=422,
        )

    try:
        bytes_2 = preprocess_set(request.image_set_2)
    except PreprocessingError as exc:
        return ComparisonResponse(
            session_id=request.session_id,
            comparison_type=request.comparison_type,
            category_hint=request.category_hint,
            user_prompt=request.user_prompt,
            verdict=None,
            confidence=None,
            category_detected=None,
            colour=None,
            design=None,
            category_match=None,
            quantity=None,
            is_product_visible_set1=None,
            is_product_visible_set2=None,
            description=None,
            model_used=model_used,
            pass1_latency_ms=None,
            pass2_latency_ms=None,
            total_latency_ms=int((time.perf_counter() - t_all) * 1000),
            json_retried=False,
            short_circuited=False,
            short_circuit_reason=None,
            audit_id=None,
            overwritten=False,
            error=f"image_set_2[{exc.image_index}]: {exc.message}",
            status_code=422,
        )

    b64_batch = to_base64_strings(bytes_1 + bytes_2)

    # STEP 3 — visibility-only pass; must precede attribute comparison.
    pass1 = await run_pass1(
        request.image_set_1,
        request.image_set_2,
        preprocessed_b64=b64_batch,
    )

    # STEP 4 — flatten per-image labels for rollup rules.
    s1_scores = _visibility_strings(pass1.set_1_visibility)
    s2_scores = _visibility_strings(pass1.set_2_visibility)

    # STEP 5 — cheap gate: skip Pass 2 if either side fails visibility policy.
    rollup = rollup_both_sets(s1_scores, s2_scores)
    if not rollup["should_run_pass2"]:
        reason = rollup["short_circuit_reason"]
        audit_id = _new_audit_id()
        record = AuditRecord(
            audit_id=audit_id,
            session_id=request.session_id,
            comparison_type=request.comparison_type,
            category_hint=request.category_hint,
            category_detected=None,
            verdict="inconclusive",
            confidence="low",
            colour=None,
            design=None,
            category_match=None,
            quantity=None,
            vis_set1=json.dumps(pass1.set_1_visibility),
            vis_set2=json.dumps(pass1.set_2_visibility),
            description=reason,
            user_prompt=request.user_prompt or None,
            model_used=model_used,
            pass1_latency_ms=pass1.latency_ms,
            pass2_latency_ms=None,
            total_latency_ms=int((time.perf_counter() - t_all) * 1000),
            json_retried=False,
            short_circuited=True,
            overwritten=False,
            created_at=None,
            updated_at=None,
        )
        overwritten = await save_audit(record)
        return ComparisonResponse(
            session_id=request.session_id,
            comparison_type=request.comparison_type,
            category_hint=request.category_hint,
            user_prompt=request.user_prompt,
            verdict="inconclusive",
            confidence="low",
            category_detected=None,
            colour=None,
            design=None,
            category_match=None,
            quantity=None,
            is_product_visible_set1=None,
            is_product_visible_set2=None,
            description=reason,
            model_used=model_used,
            pass1_latency_ms=pass1.latency_ms,
            pass2_latency_ms=None,
            total_latency_ms=int((time.perf_counter() - t_all) * 1000),
            json_retried=False,
            short_circuited=True,
            short_circuit_reason=reason,
            audit_id=audit_id,
            overwritten=overwritten,
            error=None,
            status_code=200,
        )

    # STEP 6 — full comparison only when rollup allows Pass 2.
    vis_ctx = _visibility_context_blob(pass1)
    pass2 = await run_pass2(
        request.image_set_1,
        request.image_set_2,
        request.comparison_type,
        request.category_hint,
        vis_ctx,
        request.user_prompt,
        preprocessed_b64=b64_batch,
    )

    # STEP 7 — deterministic confidence from pipeline signals (never model text).
    signals = ConfidenceSignals(
        any_partial_image=rollup["any_partial_overall"],
        category_hint_provided=_category_hint_provided(request.category_hint),
        cant_say_count=count_cant_say(pass2),
        json_retried=pass2.json_retried,
    )
    level = compute_confidence(signals)
    confidence_str = level.value

    total_ms = int((time.perf_counter() - t_all) * 1000)

    # STEP 8 — persist for compliance / analytics; ``session_id`` is idempotent key.
    audit_id = _new_audit_id()
    record = AuditRecord(
        audit_id=audit_id,
        session_id=request.session_id,
        comparison_type=request.comparison_type,
        category_hint=request.category_hint,
        category_detected=pass2.category_detected,
        verdict=pass2.verdict,
        confidence=confidence_str,
        colour=pass2.colour,
        design=pass2.design,
        category_match=pass2.category_match,
        quantity=pass2.quantity,
        vis_set1=json.dumps(pass1.set_1_visibility),
        vis_set2=json.dumps(pass1.set_2_visibility),
        description=pass2.description,
        user_prompt=request.user_prompt or None,
        model_used=model_used,
        pass1_latency_ms=pass1.latency_ms,
        pass2_latency_ms=pass2.latency_ms,
        total_latency_ms=total_ms,
        json_retried=pass2.json_retried,
        short_circuited=False,
        overwritten=False,
        created_at=None,
        updated_at=None,
    )
    overwritten = await save_audit(record)

    return ComparisonResponse(
        session_id=request.session_id,
        comparison_type=request.comparison_type,
        category_hint=request.category_hint,
        user_prompt=request.user_prompt,
        verdict=pass2.verdict,
        confidence=confidence_str,
        category_detected=pass2.category_detected,
        colour=pass2.colour,
        design=pass2.design,
        category_match=pass2.category_match,
        quantity=pass2.quantity,
        is_product_visible_set1=pass2.is_product_visible_set1,
        is_product_visible_set2=pass2.is_product_visible_set2,
        description=pass2.description,
        model_used=model_used,
        pass1_latency_ms=pass1.latency_ms,
        pass2_latency_ms=pass2.latency_ms,
        total_latency_ms=total_ms,
        json_retried=pass2.json_retried,
        short_circuited=False,
        short_circuit_reason=None,
        audit_id=audit_id,
        overwritten=overwritten,
        error=None,
        status_code=200,
    )


async def run_visibility_check(image: str) -> dict[str, Any]:
    """
    Single-image visibility probe: one real frame in set 1, two tiny placeholders in set 2.

    This keeps Pass 1’s multimodal contract (two groups) without requiring a second
    real product photo for the health-check endpoint.
    """
    dummy_side = [_MINI_JPEG_DATA_URL, _MINI_JPEG_DATA_URL]
    b_user = preprocess_set([image])
    b_dummy = preprocess_set(dummy_side)
    b64 = to_base64_strings(b_user + b_dummy)

    pass1 = await run_pass1([image], dummy_side, preprocessed_b64=b64)
    scores = _visibility_strings(pass1.set_1_visibility)
    primary = scores[0] if scores else "not_visible"
    return {
        "visibility": primary,
        "set_1_visibility": pass1.set_1_visibility,
        "set_2_visibility": pass1.set_2_visibility,
        "latency_ms": pass1.latency_ms,
    }
