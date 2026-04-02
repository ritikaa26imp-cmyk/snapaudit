"""
HTTP routes for SnapAudit.

All paths live under ``/api/v1``. Static routes like ``/audits/export`` are
registered **before** ``/audits/{audit_id}`` so ``export`` is not captured as
an ``audit_id``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from snapaudit.api.schemas import (
    AuditListResponse,
    CompareRequest,
    CompareResponse,
    ErrorResponse,
    VisibilityRequest,
    VisibilityResponse,
)
from snapaudit.audit.log import export_audits_csv, get_audit, list_audits
from snapaudit.inference.model import get_active_model
from snapaudit.pipeline.orchestrator import (
    ComparisonRequest,
    ComparisonResponse,
    ComparisonValidationError,
    run_comparison,
    run_visibility_check,
)

router = APIRouter(prefix="/api/v1", tags=["snapaudit"])


def _categories_yaml_path() -> Path:
    """Repo-root ``policies/categories.yaml`` (same file the inference stack reads)."""
    return Path(__file__).resolve().parents[2] / "policies" / "categories.yaml"


def _comparison_to_compare_response(out: ComparisonResponse) -> CompareResponse:
    """Map internal pipeline output to the public :class:`CompareResponse` shape."""
    if out.audit_id is None or out.verdict is None or out.confidence is None:
        raise ValueError("incomplete comparison result for API response")
    return CompareResponse(
        audit_id=out.audit_id,
        session_id=out.session_id,
        comparison_type=out.comparison_type,
        category_detected=out.category_detected,
        colour=out.colour,
        design=out.design,
        category_match=out.category_match,
        quantity=out.quantity,
        is_product_visible_set1=out.is_product_visible_set1,
        is_product_visible_set2=out.is_product_visible_set2,
        confidence=out.confidence,
        verdict=out.verdict,
        description=out.description,
        model_used=out.model_used or "",
        total_latency_ms=out.total_latency_ms or 0,
        overwritten=out.overwritten,
        short_circuited=out.short_circuited,
        short_circuit_reason=out.short_circuit_reason,
    )


@router.post(
    "/compare",
    response_model=None,
    summary="Run catalog vs return / pickup comparison",
    responses={
        200: {"description": "Comparison completed", "model": CompareResponse},
        400: {"description": "Validation failed", "model": ErrorResponse},
        422: {"description": "Image preprocessing failed", "model": ErrorResponse},
    },
)
async def compare(body: CompareRequest) -> CompareResponse | JSONResponse:
    """
    Validates input, preprocesses images, runs Pass 1 → rollup → Pass 2, saves audit.

    **400** — request failed :func:`validate_request` (bad session, counts, etc.).
    **422** — image decode/resize failed after validation.
    """
    internal = ComparisonRequest(
        session_id=body.session_id,
        comparison_type=body.comparison_type,
        image_set_1=body.image_set_1,
        image_set_2=body.image_set_2,
        category_hint=body.category_hint,
        user_prompt=body.user_prompt,
    )
    try:
        out = await run_comparison(internal)
    except ComparisonValidationError as exc:
        payload = ErrorResponse(
            error="validation_error",
            message=exc.detail.message,
            field=exc.detail.field,
        )
        return JSONResponse(status_code=400, content=payload.model_dump())

    if out.status_code == 422:
        payload = ErrorResponse(
            error="preprocessing_error",
            message=out.error or "Image preprocessing failed",
            field=None,
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    return _comparison_to_compare_response(out)


@router.get(
    "/audits",
    response_model=AuditListResponse,
    summary="List audits with optional filters",
)
async def audits_list(
    category: str | None = Query(None, description="Match detected or hint category"),
    verdict: str | None = None,
    confidence: str | None = None,
    from_date: str | None = Query(None, description="ISO timestamp lower bound on created_at"),
    to_date: str | None = Query(None, description="ISO timestamp upper bound on created_at"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
) -> AuditListResponse:
    """Paginated audit history (newest first)."""
    data = await list_audits(
        category=category,
        verdict=verdict,
        confidence=confidence,
        from_date=from_date,
        to_date=to_date,
        page=page,
        per_page=per_page,
    )
    return AuditListResponse(**data)


@router.get(
    "/audits/export",
    summary="Download audits as CSV",
)
async def audits_export(
    category: str | None = Query(None),
    verdict: str | None = None,
    confidence: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> StreamingResponse:
    """Same filters as ``GET /audits`` but returns the full matching set as CSV."""
    csv_text = await export_audits_csv(
        {
            "category": category,
            "verdict": verdict,
            "confidence": confidence,
            "from_date": from_date,
            "to_date": to_date,
        }
    )
    return StreamingResponse(
        iter([csv_text.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="snapaudit_export.csv"',
        },
    )


@router.get(
    "/audits/{audit_id}",
    summary="Fetch one audit by id",
)
async def audits_get(audit_id: str) -> dict[str, Any]:
    """Return the stored audit row as JSON (booleans normalized)."""
    row = await get_audit(audit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="audit not found")
    return row


@router.post(
    "/visibility",
    response_model=VisibilityResponse,
    summary="Single-image visibility check",
)
async def visibility(body: VisibilityRequest) -> VisibilityResponse:
    """Runs Pass 1 on one real frame plus internal placeholders (health / probes)."""
    data = await run_visibility_check(body.image)
    return VisibilityResponse(
        visibility=str(data["visibility"]),
        model_used=get_active_model(),
        latency_ms=int(data["latency_ms"]),
    )


@router.get("/health", summary="Liveness and configured model")
async def health() -> dict[str, str]:
    """Cheap endpoint for load balancers and local dev."""
    return {"status": "ok", "active_model": get_active_model()}


@router.get(
    "/policy/categories",
    summary="Parsed category policies for the Policy UI",
)
async def policy_categories() -> dict[str, Any]:
    """Return ``policies/categories.yaml`` as JSON for the read-only Policy page."""
    path = _categories_yaml_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="categories policy file not found")
    with path.open("rb") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="invalid policy YAML")
    return data
