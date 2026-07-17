from __future__ import annotations

import html
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


PROCESS_LABELS = (
    "导入评论资产",
    "需求生成",
    "知识库概览",
    "需求-功能-结构图谱",
    "设计方案",
    "工业设计 Prompt",
    "AI 效果图",
)


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def brand_html() -> str:
    return """
<div class="v2-brand">
  <div class="v2-brand-mark" role="img" aria-label="AI 品牌标识"></div>
  <div class="v2-brand-copy">
    <strong>产品评论知识库智能体</strong>
    <span>私有设计决策与生成工作台 V2</span>
  </div>
</div>
"""


def status_bar_html(
    *, database: str, text_model: str, image_model: str, healthy: bool
) -> str:
    health_class = "" if healthy else " off"
    health_text = "正常" if healthy else "需检查"
    return f"""
<section class="v2-topbar" aria-label="服务状态">
  <div class="v2-topbar-title">
    <strong>产品评论知识库智能体</strong>
    <span>从真实用户评论到设计方案与产品效果图</span>
  </div>
  <div class="v2-status-row">
    <span class="v2-status-pill"><i class="v2-status-dot"></i>数据库：<b>{_escape(database)}</b></span>
    <span class="v2-status-pill"><i class="v2-status-dot violet"></i>文本：<b>{_escape(text_model)}</b></span>
    <span class="v2-status-pill"><i class="v2-status-dot violet"></i>图像：<b>{_escape(image_model)}</b></span>
    <span class="v2-status-pill"><i class="v2-status-dot{health_class}"></i>服务：<b>{health_text}</b></span>
  </div>
</section>
"""


def process_bar_html(
    *, active_index: int, completed_indices: Iterable[int] = ()
) -> str:
    completed = set(completed_indices)
    parts = ['<nav class="v2-process" aria-label="生成流程">']
    for index, label in enumerate(PROCESS_LABELS):
        state = " active" if index == active_index else " done" if index in completed else ""
        aria = ' aria-current="step"' if index == active_index else ""
        number = str(index + 1)
        parts.append(
            f'<div class="v2-process-step{state}"{aria}>'
            f'<span class="v2-process-index">{number}</span>'
            f'<span class="v2-process-label">{_escape(label)}</span>'
            "</div>"
        )
    parts.append("</nav>")
    return "".join(parts)


def panel_open_html(title: str, hint: str = "") -> str:
    return (
        '<section class="v2-panel"><div class="v2-panel-title">'
        f"<strong>{_escape(title)}</strong><span>{_escape(hint)}</span>"
        "</div>"
    )


def metric_grid_html(metrics: Sequence[tuple[str, Any, str, str]]) -> str:
    allowed_tones = {"blue", "cyan", "violet", "amber"}
    cards = []
    for label, value, hint, tone in metrics:
        safe_tone = tone if tone in allowed_tones else "blue"
        cards.append(
            f'<article class="v2-metric {safe_tone}" data-kind="metric">'
            f'<span class="v2-metric-label">{_escape(label)}</span>'
            f'<strong class="v2-metric-value">{_escape(value)}</strong>'
            f'<span class="v2-metric-hint">{_escape(hint)}</span>'
            "</article>"
        )
    return '<div class="v2-metrics">' + "".join(cards) + "</div>"


def action_grid_html(actions: Sequence[tuple[str, str, str]]) -> str:
    allowed_tones = {"blue", "violet", "green", "amber"}
    cards = []
    for title, description, tone in actions:
        safe_tone = tone if tone in allowed_tones else "blue"
        cards.append(
            f'<article class="v2-action-card {safe_tone}">'
            f"<strong>{_escape(title)}</strong><span>{_escape(description)}</span>"
            "</article>"
        )
    return '<div class="v2-action-grid">' + "".join(cards) + "</div>"


def product_rows_html(products: Sequence[Mapping[str, Any]]) -> str:
    if not products:
        return '<div class="v2-empty">还没有产品资产，请先导入评论数据。</div>'
    rows = []
    for product in products:
        rows.append(
            '<article class="v2-product-row">'
            f'<strong>{_escape(product.get("name", "未命名产品"))}</strong>'
            f'<span>评论 {_escape(product.get("comments", 0))} 条</span>'
            f'<span>需求 {_escape(product.get("requirements", 0))} 条</span>'
            f'<span>更新 {_escape(product.get("updated_at", "—"))}</span>'
            "</article>"
        )
    return "".join(rows)


def mascot_html() -> str:
    return '<div class="v2-mascot" role="img" aria-label="AI 工作台助手"></div>'


def login_intro_html() -> str:
    return """
<div class="v2-login-head">
  <div class="v2-login-logo" role="img" aria-label="AI 品牌标识"></div>
  <h2>进入私有设计工作台</h2>
  <p>单用户登录 · 独立知识库 · 生成记录可追溯</p>
</div>
"""
