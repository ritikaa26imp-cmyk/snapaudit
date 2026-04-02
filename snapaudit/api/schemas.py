"""
Pydantic models for the public REST API.

These types are the contract for clients; they intentionally mirror the
orchestrator’s domain objects but stay JSON-serializable and version-stable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    """Start a two-set product comparison (URLs and/or embedded base64)."""

    session_id: str
    comparison_type: str
    category_hint: str = "auto"
    image_set_1: list[str]
    image_set_2: list[str]
    user_prompt: str = ""


class CompareResponse(BaseModel):
    """Successful comparison outcome (audit row + model outputs)."""

    audit_id: str
    session_id: str
    comparison_type: str
    category_detected: str | None
    colour: str | None
    design: str | None
    category_match: str | None
    quantity: str | None
    is_product_visible_set1: str | None
    is_product_visible_set2: str | None
    confidence: str
    verdict: str
    description: str | None
    model_used: str
    total_latency_ms: int
    overwritten: bool
    short_circuited: bool = False
    short_circuit_reason: str | None = None


class VisibilityRequest(BaseModel):
    """Single-image visibility probe."""

    image: str


class VisibilityResponse(BaseModel):
    """Pass 1 visibility label for the primary frame."""

    visibility: str
    model_used: str
    latency_ms: int


class ErrorResponse(BaseModel):
    """Machine-readable error envelope for 4xx responses."""

    error: str
    message: str
    field: str | None = None


class AuditListResponse(BaseModel):
    """Paginated audit query result."""

    items: list[dict] = Field(default_factory=list)
    total: int
    page: int
    per_page: int
