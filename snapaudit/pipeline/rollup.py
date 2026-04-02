"""
Roll up per-image visibility from Pass 1 to decide whether Pass 2 may run.

Two-image sets use a **strict** rule (every frame must be usable). Three-image
sets use a **majority** rule (at least two frames must be usable). If either
side of the comparison fails its rollup, we short-circuit to inconclusive
instead of running Pass 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypedDict


class VisibilityScore(str, Enum):
    """Per-image visibility label from Pass 1."""

    visible = "visible"
    partial = "partial"
    not_visible = "not_visible"


@dataclass(frozen=True, slots=True)
class SetVisibilityResult:
    """Outcome of applying rollup rules to one image set."""

    passes: bool
    """True if this set meets the 2-image strict or 3-image majority rule."""

    any_partial: bool
    """True if at least one image in the set was ``partial`` (still counts as a pass)."""

    failed_indices: list[int]
    """Indices where the score was ``not_visible``."""

    score_summary: str
    """Human-readable counts, e.g. ``\"2/3 visible or partial\"``."""


class RollupOutcome(TypedDict):
    """Return shape of :func:`rollup_both_sets`."""

    should_run_pass2: bool
    set1_result: SetVisibilityResult
    set2_result: SetVisibilityResult
    short_circuit_reason: str
    """Empty when ``should_run_pass2`` is True; otherwise why Pass 2 was skipped."""

    any_partial_overall: bool


def _parse_score(raw: str) -> VisibilityScore:
    """Map API / model strings to :class:`VisibilityScore`."""
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if key == "notvisible":
        key = "not_visible"
    try:
        return VisibilityScore(key)
    except ValueError as exc:
        raise ValueError(f"unknown visibility score: {raw!r}") from exc


def _good(score: VisibilityScore) -> bool:
    """``visible`` and ``partial`` count toward passing; ``not_visible`` does not."""
    return score in (VisibilityScore.visible, VisibilityScore.partial)


def set_passes_visibility(scores: list[str]) -> SetVisibilityResult:
    """
    Apply Pass 1 rollup rules for a single image set.

    **Two images (strict):** both must be ``visible`` or ``partial``. If either
    is ``not_visible``, the set fails.

    **Three images (majority):** at least **two** must be ``visible`` or
    ``partial``. Equivalently, at most one ``not_visible`` is allowed.

    ``not_visible`` increments :attr:`SetVisibilityResult.failed_indices`.
    ``partial`` does not fail the set but sets ``any_partial=True``.
    """
    n = len(scores)
    if n not in (2, 3):
        raise ValueError(
            f"visibility rollup expects 2 or 3 scores, got {n}"
        )

    parsed = [_parse_score(s) for s in scores]
    failed_indices = [i for i, sc in enumerate(parsed) if sc is VisibilityScore.not_visible]
    any_partial = any(sc is VisibilityScore.partial for sc in parsed)

    good_count = sum(1 for sc in parsed if _good(sc))
    score_summary = f"{good_count}/{n} visible or partial"

    if n == 2:
        # Strict: both frames must contribute usable signal.
        passes = good_count == 2
    else:
        # Majority: at least two of three frames must be usable.
        passes = good_count >= 2

    return SetVisibilityResult(
        passes=passes,
        any_partial=any_partial,
        failed_indices=failed_indices,
        score_summary=score_summary,
    )


def _short_circuit_message(set_label: str, result: SetVisibilityResult) -> str:
    """Build the canonical explanation for one failing set."""
    # ``score_summary`` is shaped like ``"1/2 visible or partial"``.
    _, rest = result.score_summary.split("/", 1)
    total = int(rest.split()[0])
    not_visible_count = len(result.failed_indices)
    return (
        f"{set_label} failed visibility rollup: "
        f"{not_visible_count} of {total} images assessed as not_visible"
    )


def rollup_both_sets(
    set1_scores: list[str],
    set2_scores: list[str],
) -> RollupOutcome:
    """
    Roll up both sides of the comparison.

    Pass 2 should run only when **both** sets pass their visibility rules.
    ``short_circuit_reason`` is empty when Pass 2 runs; otherwise it describes
    the first failing set (or both, if both fail).
    """
    set1_result = set_passes_visibility(set1_scores)
    set2_result = set_passes_visibility(set2_scores)

    should_run_pass2 = set1_result.passes and set2_result.passes
    any_partial_overall = set1_result.any_partial or set2_result.any_partial

    short_circuit_reason = ""
    if not should_run_pass2:
        parts: list[str] = []
        if not set1_result.passes:
            parts.append(_short_circuit_message("image_set_1", set1_result))
        if not set2_result.passes:
            parts.append(_short_circuit_message("image_set_2", set2_result))
        short_circuit_reason = " ".join(parts)

    return RollupOutcome(
        should_run_pass2=should_run_pass2,
        set1_result=set1_result,
        set2_result=set2_result,
        short_circuit_reason=short_circuit_reason,
        any_partial_overall=any_partial_overall,
    )
