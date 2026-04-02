"""
Deterministic confidence from observable pipeline signals.

The vision model must not self-report confidence — callers aggregate
:class:`ConfidenceSignals` and derive a :class:`ConfidenceLevel` here only.

**Priority order matters:** ``low`` rules are evaluated first, then ``medium``,
then ``high``. An earlier rule wins over later ones (e.g. ``cant_say_count >= 3``
forces ``low`` even though ``>= 2`` would otherwise suggest ``medium``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Final confidence tier shown to the user."""

    high = "high"
    medium = "medium"
    low = "low"


@dataclass(frozen=True, slots=True)
class ConfidenceSignals:
    """Inputs collected during validation, Pass 1 rollup, and Pass 2 parsing."""

    any_partial_image: bool
    """True if any image in either set was graded ``partial`` for visibility."""

    category_hint_provided: bool
    """True when the user supplied an explicit category hint (not auto-detected)."""

    cant_say_count: int
    """How many compared attributes came back ``cant_say``."""

    json_retried: bool
    """True when Pass 2 had to retry because the model returned malformed JSON."""


def compute_confidence(signals: ConfidenceSignals) -> ConfidenceLevel:
    """
    Map signals to a confidence level using a fixed decision list.

    Order of checks (first match wins within each band):

    **Forces low** (strongest degradation — evaluated before any medium rule):

    1. ``json_retried`` — repair/retry means we trust the structured output less.
    2. ``cant_say_count >= 3`` — too many unresolved attributes; caps at low before
       the weaker ``>= 2`` medium rule is considered.

    **Forces medium** (only if no low rule fired):

    3. ``any_partial_image`` — usable but degraded imagery vs. fully visible.
    4. ``category_hint_provided is False`` — category inferred, not confirmed.
    5. ``cant_say_count >= 2`` — some ambiguity, but not enough for low unless (1–2).

    **Otherwise:** ``high`` — no retry, at most one ``cant_say``, explicit category,
    and no partial-only frames (per the rules above).
    """
    # --- Forces low (check first; overrides medium and high) ---
    if signals.json_retried:
        return ConfidenceLevel.low
    if signals.cant_say_count >= 3:
        return ConfidenceLevel.low

    # --- Forces medium (only if we did not already return low) ---
    if signals.any_partial_image:
        return ConfidenceLevel.medium
    if not signals.category_hint_provided:
        return ConfidenceLevel.medium
    if signals.cant_say_count >= 2:
        return ConfidenceLevel.medium

    return ConfidenceLevel.high


def get_confidence_explanation(signals: ConfidenceSignals) -> str:
    """
    Human-readable reason for the level :func:`compute_confidence` would return.

    Uses the **same priority order** as :func:`compute_confidence` so the text
    always matches the first rule that determined the outcome.
    """
    if signals.json_retried:
        return "JSON retry was triggered"
    if signals.cant_say_count >= 3:
        return "3 or more attributes returned cant_say"
    if signals.any_partial_image:
        return "One or more partial images in the comparison"
    if not signals.category_hint_provided:
        return "Category was auto-detected (no hint provided)"
    if signals.cant_say_count >= 2:
        return "2 or more attributes returned cant_say"
    return "All signals clear"
