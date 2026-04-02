"""
Load category rubrics from ``policies/categories.yaml`` and build Pass 1 / Pass 2
system prompts.

Keeping policy text in YAML lets ops edit rules without code changes; this
module only formats and wraps that content so the model sees consistent
structure and JSON-only outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml

# Fixed attribute order for every category block (matches the policy file).
_ATTR_ORDER: Final[tuple[str, ...]] = (
    "colour",
    "design",
    "category",
    "quantity",
)

# ---------------------------------------------------------------------------
# Paths & YAML loading
# ---------------------------------------------------------------------------


def _policies_path() -> Path:
    """``policies/categories.yaml`` at the repository root."""
    return Path(__file__).resolve().parents[2] / "policies" / "categories.yaml"


def _load_categories_document() -> dict[str, Any]:
    """Parse the full policy document (visibility defs + per-category rules)."""
    path = _policies_path()
    with path.open("rb") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"policies at {path} must parse to a mapping")
    return data


def _format_policy_block(category_name: str, rules: dict[str, Any]) -> str:
    """
    Turn one YAML ``categories.<name>`` mapping into a readable rubric string.

    Each attribute lists **match**, **mismatch**, and **cant_say** so the model
    cannot blur the three verdict types during Pass 2.
    """
    lines: list[str] = [f"Category policy: {category_name}", ""]
    for attr in _ATTR_ORDER:
        block = rules.get(attr)
        if not isinstance(block, dict):
            lines.append(f"{attr.upper()}")
            lines.append("  (no rules defined in policy file)")
            lines.append("")
            continue
        lines.append(f"{attr.upper()}")
        lines.append(f"  match: {block.get('match', '')}")
        lines.append(f"  mismatch: {block.get('mismatch', '')}")
        lines.append(f"  cant_say: {block.get('cant_say', '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# Generic rubric when the user chose **auto** or the category key is missing.
# Keeps Pass 2 usable without overfitting to a single vertical.
_FALLBACK_POLICY: Final[str] = """
Category policy: GENERIC (auto or unknown category)

COLOUR
  match: Same overall colour family; minor lighting variance allowed.
  mismatch: Clearly different colour family or dominant hue.
  cant_say: Colour cannot be judged (heavy cast, blur, or occlusion).

DESIGN
  match: Same apparent pattern/texture/construction family for the product type.
  mismatch: Clearly different pattern, structure, or style family.
  cant_say: Design cannot be judged (too little of the product visible).

CATEGORY
  match: Same broad product type (e.g. both tops, both bags) with consistent role.
  mismatch: Clearly different product type or intended use.
  cant_say: Product type cannot be determined from what is visible.

QUANTITY
  match: Same apparent piece count or set size (single vs single, same multi-pack).
  mismatch: Different piece count or obvious set vs single mismatch.
  cant_say: Count cannot be determined (stack, packaging, or occlusion).
""".strip()


def load_policy(category: str) -> str:
    """
    Return the formatted policy text for ``category``.

    Loads ``policies/categories.yaml`` on each call so edits apply without
    restart. If ``category`` is ``\"auto\"`` (case-insensitive) or absent from
    the file, returns :data:`_FALLBACK_POLICY`.
    """
    doc = _load_categories_document()
    categories = doc.get("categories")
    if not isinstance(categories, dict):
        return _FALLBACK_POLICY

    key = category.strip().lower()
    if key == "auto" or key not in categories:
        return _FALLBACK_POLICY

    raw = categories[key]
    if not isinstance(raw, dict):
        return _FALLBACK_POLICY

    return _format_policy_block(key, raw)


# ---------------------------------------------------------------------------
# Pass 1 — visibility only (no attribute comparison yet)
# ---------------------------------------------------------------------------


def build_pass1_prompt() -> str:
    """
    System prompt for Pass 1: per-image visibility only.

    We separate visibility from merchandising attributes so the model does not
    “solve” the audit in one step or hallucinate colour/design before frames
    are confirmed usable. JSON-only output keeps downstream parsing reliable.
    """
    doc = _load_categories_document()
    vis = doc.get("visibility_definitions")
    if isinstance(vis, dict):
        visible = vis.get("visible", "")
        partial = vis.get("partial", "")
        not_visible = vis.get("not_visible", "")
    else:
        visible = partial = not_visible = ""

    # Keep definitions aligned with YAML; fall back if keys are missing.
    if not visible:
        visible = (
            "product occupies ≥30% of frame, key attributes clearly discernible"
        )
    if not partial:
        partial = "product present but key attributes partially obscured"
    if not not_visible:
        not_visible = (
            "product cannot be assessed - only packaging, blank surface, "
            "or too dark/blurred"
        )

    return f"""You are a vision assistant for e-commerce quality control.

Your task in this pass is ONLY to judge how well the PRODUCT (not the model, not the background) is visible in each image.

Visibility levels (use exactly one label per image):
- visible: {visible}
- partial: {partial}
- not_visible: {not_visible}

Assess each image independently. Use the images in the order provided for each set.

Do not infer product type, colour, design, or any comparison attribute at this stage.

Respond with JSON ONLY and no other text. The JSON must validate against this exact schema:
{{
  "set_1_visibility": [
    {{"image_index": 1, "visibility": "visible|partial|not_visible"}}
  ],
  "set_2_visibility": [
    {{"image_index": 1, "visibility": "visible|partial|not_visible"}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Pass 2 — full comparison with policy + user context
# ---------------------------------------------------------------------------

_COMPARISON_INTRO: Final[dict[str, str]] = {
    "catalog_vs_icud": (
        "Comparison type: catalog_vs_icud.\n"
        "- Image set 1: catalog / listing reference images for the SKU.\n"
        "- Image set 2: ICUD (in-customer) images showing what was received."
    ),
    "catalog_vs_pickup": (
        "Comparison type: catalog_vs_pickup.\n"
        "- Image set 1: catalog / listing reference images for the SKU.\n"
        "- Image set 2: pickup / return images showing what came back."
    ),
}


def build_pass2_prompt(
    comparison_type: str,
    category: str,
    visibility_context: str,
    user_prompt: str,
) -> str:
    """
    System prompt for Pass 2: attribute-level comparison and verdict.

    Sections are ordered so the model (1) knows which side is reference vs
    customer, (2) understands multi-image sets, (3) applies the right rubric,
    (4) respects Pass 1 visibility, (5) still scores every attribute even if
    category detection disagrees, (6) optionally reads user notes without
    letting them override policy, (7) emits strict JSON.
    """
    intro = _COMPARISON_INTRO.get(
        comparison_type.strip(),
        (
            f"Comparison type: {comparison_type}.\n"
            "- Image set 1: first product image group in the request.\n"
            "- Image set 2: second product image group in the request."
        ),
    )

    policy_block = load_policy(category)

    user_section = user_prompt.strip() if user_prompt.strip() else "(none provided)"

    return f"""You are a vision assistant for e-commerce swap / mismatch detection.

{intro}

Images within each set are complementary views of the SAME product instance for that side of the comparison (different angles or distances). Use all images in a set together when judging each attribute.

--- Category policy (how to interpret match / mismatch / cant_say) ---
{policy_block}

--- Pass 1 visibility context (do not contradict these per-set visibility facts) ---
{visibility_context.strip()}

You must evaluate ALL attributes listed in the JSON schema below (colour, design, category_match, quantity) even if your detected category differs from the policy section title or from the user hint. The policy tells you how to label match vs mismatch vs cant_say; still fill every field.

--- Additional context from user (does not override the above policy) ---
{user_section}

Respond with JSON ONLY and no other text. The JSON must validate against this exact schema:
{{
  "category_detected": "saree|kurti|bag|cloth|jewellery|watch|unknown",
  "colour": "same|different|cant_say",
  "design": "same|different|cant_say",
  "category_match": "same|different|cant_say",
  "quantity": "same|different|cant_say",
  "is_product_visible_set1": "visible|partial|not_visible",
  "is_product_visible_set2": "visible|partial|not_visible",
  "verdict": "match|mismatch|inconclusive",
  "description": "what set 1 shows, what set 2 shows, which attributes match and which differ"
}}
"""

