from __future__ import annotations

import hashlib
import re
from typing import Mapping, Sequence


_REQUIRED_KEYS = (
    "render_1",
    "render_2",
    "exploded",
    "detail",
    "three_view",
    "board",
    "usage_1",
    "usage_2",
)


def _text(value: object, fallback: str = "") -> str:
    return " ".join(str(value or fallback).split())


def _constraint(constraints: Mapping[str, object], *keys: str, fallback: str) -> str:
    for key in keys:
        value = _text(constraints.get(key))
        if value:
            return value
    return fallback


def _canonical_product_id(target_product: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", target_product.lower()).strip("-")
    digest = hashlib.sha256(target_product.encode("utf-8")).hexdigest()[:10]
    return f"canonical-{normalized or 'product'}-{digest}"


def _shared_contract(target_product: str, constraints: Mapping[str, object]) -> str:
    structure = _constraint(
        constraints,
        "structure",
        "product_structure",
        fallback="the approved housing, interaction zone and serviceable internal modules",
    )
    materials = _constraint(
        constraints,
        "materials",
        "material_specification",
        fallback="durable production-ready materials with clear surface treatment",
    )
    colors = _constraint(
        constraints, "colors", fallback="one coherent primary colour and one restrained accent colour"
    )
    dimensions = _constraint(
        constraints,
        "dimensions",
        "dimension_proportion",
        fallback="the approved overall proportions and ergonomic contact zones",
    )
    functions = _constraint(
        constraints,
        "core_functions",
        "functional_requirements",
        fallback="the approved core user functions",
    )
    forbidden = _constraint(
        constraints,
        "forbidden_changes",
        "negative_constraints",
        fallback="do not add undefined functions, alternative products, branding, watermarks, or unreadable text",
    )
    return (
        "[CANONICAL PRODUCT DELIVERY CONTRACT]\n"
        f"This is the single approved product: {target_product}. Every asset must depict the exact same "
        "silhouette, component count, interaction zone, CMF, proportions and assembly logic. "
        f"Locked structure: {structure}. Locked materials and finish: {materials}. "
        f"Locked CMF: {colors}. Locked dimensions/proportions: {dimensions}. "
        f"Locked core functions: {functions}. Non-negotiable exclusions: {forbidden}.\n"
        "Do not redesign the product between images. Do not make a collage, contact sheet, product family, "
        "unrelated object, fictional logo, watermark, or illegible paragraphs. Use one physically plausible "
        "manufacturable product and preserve its identity in every image."
    )


def _asset_contract(key: str, constraints: Mapping[str, object]) -> tuple[str, list[str]]:
    dimensions = _constraint(
        constraints,
        "dimensions",
        "dimension_proportion",
        fallback="approved proportions only; do not invent numeric measurements",
    )
    cmf = _constraint(
        constraints,
        "colors",
        "materials",
        fallback="approved colour, material and finish",
    )
    if key == "render_1":
        return (
            "Hero render: show one complete product at a 45-degree three-quarter view on a clean studio "
            "background. Make the primary interaction and the locked material transitions clearly readable. "
            "Use a single product, realistic scale, stable ground contact and restrained lighting.",
            ["single complete product", "recognisable core interaction", "manufacturable CMF", "no alternate concept"],
        )
    if key == "render_2":
        return (
            "Secondary render: show the same product from a meaningfully different camera angle, not a duplicate "
            "of the hero image. Reveal a different approved functional area while retaining the identical silhouette, "
            "CMF and component count.",
            ["different useful view", "same silhouette and CMF", "same component count", "no duplicate hero composition"],
        )
    if key == "exploded":
        return (
            "Engineering exploded view: render one vertical assembly sequence in a single frame. Every separated part "
            "must be a distinct, mechanically plausible part that belongs to the next layer; show mounting direction, "
            "interfaces and stack order. Use only parts justified by the locked structure. No duplicate shells, no "
            "duplicate trays, no unexplained floating PCB, battery, wire or fastener, and no unrelated electronics. "
            "If an internal module is not specified, show one contained service module rather than inventing circuitry.",
            ["single vertical assembly sequence", "each part has an assembly relationship", "no duplicate shells or trays", "no unexplained internal electronics"],
        )
    if key == "detail":
        return (
            "Detail render: show one close-up from the same product, focused on a real join, seal, opening mechanism, "
            "interaction surface or material transition. Include crisp material texture and manufacturable part gaps; "
            "do not replace the product with a generic macro object. Use numbered callout markers only when needed, "
            "with no fabricated technical claims.",
            ["same-product close-up", "real join or interaction detail", "visible material/part-gap evidence", "no fabricated specification"],
        )
    if key == "three_view":
        return (
            "Orthographic three-view sheet: front, right-side and top views of the same product, aligned on one baseline "
            "at the same scale, with zero perspective distortion. Show only approved exterior geometry and consistent "
            "part breaks. Dimensions/proportions to communicate: "
            f"{dimensions}. Use numeric dimension callouts only where the input supplied a number; otherwise use a ratio "
            "grid and numbered markers, never invented measurements.",
            ["orthographic front/right/top", "same scale and baseline", "consistent part breaks", "no invented dimensions"],
        )
    if key == "board":
        return (
            "Final design presentation board for a review or thesis: establish one clear hero render, then show the same "
            "product's exploded view, detail, three-view, use context, CMF swatches and concise numbered callouts. CMF to "
            f"communicate: {cmf}. Keep a deliberate hierarchy, ample whitespace and a readable visual story. Use short "
            "headings or numbered labels only; no illegible paragraphs, pseudo-language or fabricated data tables.",
            ["clear review-ready hierarchy", "same-product visual set", "CMF explicitly communicated", "no illegible paragraphs"],
        )
    if key == "usage_1":
        return (
            "Usage scene one: show the approved target user naturally using the same product in a plausible primary "
            "environment. Product scale, support surface and interaction must be believable. If hands are visible, show "
            "complete fingers and natural joints; no finger may pass through the product, lid, transparent part or internal space.",
            ["plausible primary use scene", "same product at credible scale", "complete fingers and natural joints", "no impossible hand-product intersections"],
        )
    if key == "usage_2":
        return (
            "Usage scene two: tell a different but complementary moment of use from usage scene one. Keep the exact same "
            "product identity, materials and proportions, while changing the camera, user action or setting. If hands are "
            "visible, show complete fingers and natural joints; no finger may pass through the product or transparent parts.",
            ["meaningfully different scene", "same product identity", "complete fingers and natural joints", "no impossible hand-product intersections"],
        )
    return (
        "Render the approved product only, with coherent product identity and production-plausible construction.",
        ["same canonical product", "coherent construction"],
    )


def qualify_visual_delivery(
    target_product: str,
    visual_assets: Sequence[Mapping[str, object]],
    industrial_constraints: Mapping[str, object] | None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Attach a deterministic, asset-specific delivery contract before paid generation.

    The gate evaluates the delivery plan, rather than pretending it can judge provider pixels.
    Provider output still requires owner review before it is treated as final artwork.
    """

    constraints = industrial_constraints or {}
    canonical_id = _canonical_product_id(_text(target_product, "target product"))
    shared = _shared_contract(_text(target_product, "target product"), constraints)
    seen_keys: set[str] = set()
    qualified: list[dict[str, object]] = []
    for asset in visual_assets:
        current = dict(asset)
        key = _text(current.get("key"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        asset_instruction, criteria = _asset_contract(key, constraints)
        original_prompt = _text(current.get("prompt"))
        current["canonical_product_id"] = canonical_id
        current["acceptance_criteria"] = criteria
        current["prompt"] = "\n\n".join(
            part for part in (shared, asset_instruction, original_prompt) if part
        )
        qualified.append(current)

    missing = [key for key in _REQUIRED_KEYS if key not in seen_keys]
    return qualified, {
        "version": "visual-delivery-v1",
        "status": "pass" if not missing else "needs_revision",
        "canonical_product_id": canonical_id,
        "planned_asset_count": len(qualified),
        "required_asset_keys": list(_REQUIRED_KEYS),
        "missing_requirements": missing,
        "review_note": "The plan is contract-checked before generation. Final pixels still require owner review for engineering fidelity and visual consistency.",
    }
