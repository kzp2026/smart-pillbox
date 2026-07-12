from __future__ import annotations

from typing import Any


PROMPT_SECTIONS = (
    "产品定位",
    "核心需求",
    "产品结构锁定",
    "材料与工艺",
    "尺寸比例",
    "视觉风格",
    "镜头与构图",
    "应用场景",
    "禁止修改项",
)


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _requirement_summary(context: dict[str, Any] | None) -> str:
    requirements = (context or {}).get("requirements", [])
    lines: list[str] = []
    for item in requirements[:4]:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        description = _text(item.get("description"))
        if title and description:
            lines.append(f"{title}：{description}")
        elif title:
            lines.append(title)
    return "；".join(lines)


def normalize_industrial_design_constraints(
    constraints: dict[str, object] | None,
    *,
    product_name: str,
    demand_text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Normalize user-entered industrial-design constraints without database coupling."""
    raw = constraints or {}
    normalized_product = _text(raw.get("product_name")) or _text(product_name) or "目标产品"
    user_needs = _text(raw.get("user_needs")) or _text(demand_text) or "围绕目标用户的真实使用痛点进行设计。"
    functional_requirements = _text(raw.get("functional_requirements"))
    evidence_requirements = _requirement_summary(context)
    core_requirements = "；".join(
        value for value in (user_needs, functional_requirements, evidence_requirements) if value
    )
    product_structure = _text(raw.get("product_structure")) or "保持完整产品主体、核心功能组件、交互区域与维护结构之间的既定关系。"
    material_specification = _text(raw.get("material_specification")) or "依据真实使用环境选择耐用、易清洁、适合量产的材料，并明确表面处理。"
    dimension_proportion = _text(raw.get("dimension_proportion")) or "保持整体长宽高、关键部件尺度和人体工程接触区域比例协调，避免拉伸、压缩或比例失真。"
    application_scenario = _text(raw.get("application_scenario")) or user_needs
    visual_style = _text(raw.get("visual_style")) or "工业设计效果图，KeyShot 级写实渲染，产品摄影质感，4K 高清，柔和工作室布光。"
    camera_angle = _text(raw.get("camera_angle")) or "45 度三分之四主视角；需要工程表达时使用正视、侧视、顶视或单张立体爆炸图。"
    negative_constraints = _text(raw.get("negative_constraints")) or (
        "不改变产品结构，不改变尺寸比例，不增加未定义功能；保持统一产品设计语言、材料语言、色彩与关键组件数量；"
        "不生成拼贴图、九宫格、多个产品方案、无关产品、文字水印或品牌标志。"
    )
    return {
        "product_name": normalized_product,
        "user_needs": user_needs,
        "functional_requirements": functional_requirements or "功能需求以用户需求和知识库证据为准。",
        "product_structure": product_structure,
        "material_specification": material_specification,
        "dimension_proportion": dimension_proportion,
        "application_scenario": application_scenario,
        "visual_style": visual_style,
        "camera_angle": camera_angle,
        "negative_constraints": negative_constraints,
        "core_requirements": core_requirements or user_needs,
    }


def build_industrial_design_prompt(
    constraints: dict[str, object] | None,
    *,
    product_name: str,
    demand_text: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, str]]:
    """Build the fixed, reusable prompt block injected into every visual asset."""
    data = normalize_industrial_design_constraints(
        constraints,
        product_name=product_name,
        demand_text=demand_text,
        context=context,
    )
    sections = [
        ("产品定位", f"{data['product_name']}面向的用户与使用情境：{data['user_needs']}。应用场景：{data['application_scenario']}。"),
        ("核心需求", data["core_requirements"]),
        ("产品结构锁定", f"固定整体形态、不可改变的核心结构与关键组件：{data['product_structure']}。多次生成必须复用同一轮廓、组件数量、交互区域与装配关系。"),
        ("材料与工艺", data["material_specification"]),
        ("尺寸比例", data["dimension_proportion"]),
        ("视觉风格", data["visual_style"]),
        ("镜头与构图", data["camera_angle"]),
        ("应用场景", data["application_scenario"]),
        ("禁止修改项", data["negative_constraints"]),
    ]
    prompt = "\n\n".join(f"【{title}】\n{body}" for title, body in sections)
    return prompt, data
