"""
SQLite audit trail for SnapAudit runs.

**Overwrite semantics:** the API treats ``session_id`` as the idempotency key.
The first save for a session **INSERT**s a row; any later save with the same
``session_id`` **UPDATE**s that row in place, preserves ``audit_id`` and
``created_at``, sets ``overwritten = TRUE``, and refreshes ``updated_at``.
This matches “latest result wins” for retries and client resubmits without
duplicating history rows.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Mapping, TypedDict

import aiosqlite
import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path() -> Path:
    return _repo_root() / "config.yaml"


def _load_audit_db_path() -> Path:
    with _config_path().open("rb") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg, dict):
        raise ValueError("config.yaml must parse to a mapping")
    raw = cfg.get("audit_db_path", "snapaudit/audit/snapaudit.db")
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return _repo_root() / path


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AuditRecord:
    """One row in ``audits`` — mirrors the table schema."""

    audit_id: str
    session_id: str
    comparison_type: str
    category_hint: str | None
    category_detected: str | None
    verdict: str
    confidence: str
    colour: str | None
    design: str | None
    category_match: str | None
    quantity: str | None
    vis_set1: str | None
    vis_set2: str | None
    description: str | None
    user_prompt: str | None
    model_used: str
    pass1_latency_ms: int | None
    pass2_latency_ms: int | None
    total_latency_ms: int | None
    json_retried: bool
    short_circuited: bool
    overwritten: bool
    created_at: str | None
    updated_at: str | None


class AuditExportFilters(TypedDict, total=False):
    """Optional filters shared by listing and CSV export."""

    category: str | None
    verdict: str | None
    confidence: str | None
    from_date: str | None
    to_date: str | None


_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "audit_id",
    "session_id",
    "comparison_type",
    "category_hint",
    "category_detected",
    "verdict",
    "confidence",
    "colour",
    "design",
    "category_match",
    "quantity",
    "vis_set1",
    "vis_set2",
    "description",
    "user_prompt",
    "model_used",
    "pass1_latency_ms",
    "pass2_latency_ms",
    "total_latency_ms",
    "json_retried",
    "short_circuited",
    "overwritten",
    "created_at",
    "updated_at",
)


_CREATE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS audits (
    audit_id         TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    comparison_type  TEXT NOT NULL,
    category_hint    TEXT,
    category_detected TEXT,
    verdict          TEXT NOT NULL,
    confidence       TEXT NOT NULL,
    colour           TEXT,
    design           TEXT,
    category_match   TEXT,
    quantity         TEXT,
    vis_set1         TEXT,
    vis_set2         TEXT,
    description      TEXT,
    user_prompt      TEXT,
    model_used       TEXT NOT NULL,
    pass1_latency_ms INTEGER,
    pass2_latency_ms INTEGER,
    total_latency_ms INTEGER,
    json_retried     BOOLEAN DEFAULT FALSE,
    short_circuited  BOOLEAN DEFAULT FALSE,
    overwritten      BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP NOT NULL,
    updated_at       TIMESTAMP NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("json_retried", "short_circuited", "overwritten"):
        if key in d and d[key] is not None:
            d[key] = bool(d[key])
    return d


def _filter_sql_and_params(
    category: str | None,
    verdict: str | None,
    confidence: str | None,
    from_date: str | None,
    to_date: str | None,
) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []
    if category is not None:
        parts.append("(category_detected = ? OR category_hint = ?)")
        params.extend([category, category])
    if verdict is not None:
        parts.append("verdict = ?")
        params.append(verdict)
    if confidence is not None:
        parts.append("confidence = ?")
        params.append(confidence)
    if from_date is not None:
        parts.append("created_at >= ?")
        params.append(from_date)
    if to_date is not None:
        parts.append("created_at <= ?")
        params.append(to_date)
    where = " AND ".join(parts) if parts else "1 = 1"
    return where, params


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create ``audits`` (and parent directories) if they do not exist yet."""
    db_path = _load_audit_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(_CREATE_SQL)
        await conn.commit()


async def save_audit(audit: AuditRecord) -> bool:
    """
    Persist ``audit``.

    If a row with the same ``session_id`` exists, update **all** columns except
    ``audit_id`` and ``created_at``, force ``overwritten = TRUE``, set
    ``updated_at`` to now, and return ``True`` (overwrite). Otherwise insert a
    new row with ``created_at`` / ``updated_at`` set to now and return ``False``.
    """
    db_path = _load_audit_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = _utc_now_iso()

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT audit_id FROM audits WHERE session_id = ? LIMIT 1",
            (audit.session_id,),
        )
        existing = await cur.fetchone()

        if existing is not None:
            await conn.execute(
                """
                UPDATE audits SET
                    session_id = ?,
                    comparison_type = ?,
                    category_hint = ?,
                    category_detected = ?,
                    verdict = ?,
                    confidence = ?,
                    colour = ?,
                    design = ?,
                    category_match = ?,
                    quantity = ?,
                    vis_set1 = ?,
                    vis_set2 = ?,
                    description = ?,
                    user_prompt = ?,
                    model_used = ?,
                    pass1_latency_ms = ?,
                    pass2_latency_ms = ?,
                    total_latency_ms = ?,
                    json_retried = ?,
                    short_circuited = ?,
                    overwritten = 1,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    audit.session_id,
                    audit.comparison_type,
                    audit.category_hint,
                    audit.category_detected,
                    audit.verdict,
                    audit.confidence,
                    audit.colour,
                    audit.design,
                    audit.category_match,
                    audit.quantity,
                    audit.vis_set1,
                    audit.vis_set2,
                    audit.description,
                    audit.user_prompt,
                    audit.model_used,
                    audit.pass1_latency_ms,
                    audit.pass2_latency_ms,
                    audit.total_latency_ms,
                    audit.json_retried,
                    audit.short_circuited,
                    now,
                    audit.session_id,
                ),
            )
            await conn.commit()
            return True

        await conn.execute(
            """
            INSERT INTO audits (
                audit_id, session_id, comparison_type, category_hint, category_detected,
                verdict, confidence, colour, design, category_match, quantity,
                vis_set1, vis_set2, description, user_prompt, model_used,
                pass1_latency_ms, pass2_latency_ms, total_latency_ms,
                json_retried, short_circuited, overwritten,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit.audit_id,
                audit.session_id,
                audit.comparison_type,
                audit.category_hint,
                audit.category_detected,
                audit.verdict,
                audit.confidence,
                audit.colour,
                audit.design,
                audit.category_match,
                audit.quantity,
                audit.vis_set1,
                audit.vis_set2,
                audit.description,
                audit.user_prompt,
                audit.model_used,
                audit.pass1_latency_ms,
                audit.pass2_latency_ms,
                audit.total_latency_ms,
                audit.json_retried,
                audit.short_circuited,
                audit.overwritten,
                now,
                now,
            ),
        )
        await conn.commit()
        return False


async def get_audit(audit_id: str) -> dict[str, Any] | None:
    """Return one audit row as a dict, or ``None`` if missing."""
    db_path = _load_audit_db_path()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM audits WHERE audit_id = ?",
            (audit_id,),
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None


async def list_audits(
    category: str | None = None,
    verdict: str | None = None,
    confidence: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """
    Filter audits with optional equality / range predicates and paginate.

    ``category`` matches either ``category_detected`` or ``category_hint``.
    ``from_date`` / ``to_date`` compare to ``created_at`` (inclusive), using the
    stored ISO-8601 strings.
    """
    if page < 1:
        page = 1
    per_page = max(1, min(per_page, 500))
    where, params = _filter_sql_and_params(
        category, verdict, confidence, from_date, to_date
    )
    offset = (page - 1) * per_page

    db_path = _load_audit_db_path()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row

        count_cur = await conn.execute(
            f"SELECT COUNT(*) AS c FROM audits WHERE {where}",
            params,
        )
        total_row = await count_cur.fetchone()
        total = int(total_row["c"]) if total_row else 0

        cur = await conn.execute(
            f"""
            SELECT * FROM audits
            WHERE {where}
            ORDER BY datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (*params, per_page, offset),
        )
        rows = await cur.fetchall()
        items = [_row_to_dict(r) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


async def export_audits_csv(filters: AuditExportFilters | None = None) -> str:
    """
    Return all rows matching ``filters`` as CSV (header + one row per audit).

    ``filters`` uses the same keys as :func:`list_audits` (without pagination).
    ``None`` means no filtering (export everything).
    """
    f = filters or {}
    where, params = _filter_sql_and_params(
        f.get("category"),
        f.get("verdict"),
        f.get("confidence"),
        f.get("from_date"),
        f.get("to_date"),
    )

    db_path = _load_audit_db_path()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"""
            SELECT * FROM audits
            WHERE {where}
            ORDER BY datetime(created_at) DESC
            """,
            params,
        )
        rows = await cur.fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(list(_AUDIT_COLUMNS))
    for row in rows:
        d = _row_to_dict(row)
        writer.writerow([d.get(col) for col in _AUDIT_COLUMNS])
    return buffer.getvalue()
