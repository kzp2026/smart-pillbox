from __future__ import annotations

import html
from collections import defaultdict

import pandas as pd


LAYER_ORDER = ["Product", "Evidence", "Requirement", "Function", "Structure"]
LAYER_TITLES = {
    "Product": "产品对象",
    "Evidence": "评论证据 / 主题",
    "Requirement": "用户需求",
    "Function": "功能参数",
    "Structure": "结构方案",
}
TYPE_TO_LAYER = {
    "Product": "Product",
    "Topic": "Evidence",
    "Keyword": "Evidence",
    "Requirement": "Requirement",
    "Function": "Function",
    "Structure": "Structure",
}
TYPE_TITLES = {
    "Product": "产品",
    "Topic": "主题",
    "Keyword": "关键词",
    "Requirement": "需求",
    "Function": "功能",
    "Structure": "结构",
}
TYPE_COLORS = {
    "Product": "#4D8DFF",
    "Topic": "#8B5CF6",
    "Keyword": "#EF6C4D",
    "Requirement": "#31B56A",
    "Function": "#F59E42",
    "Structure": "#25B8B6",
}


def _safe(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _truncate(value: object, limit: int = 13) -> str:
    text = str(value if value is not None else "").strip()
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _degree_map(rels_df: pd.DataFrame) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    if rels_df.empty:
        return degrees
    for _, rel in rels_df.iterrows():
        source_id = str(rel.get("source_id", ""))
        target_id = str(rel.get("target_id", ""))
        if source_id:
            degrees[source_id] += 1
        if target_id:
            degrees[target_id] += 1
    return degrees


def _select_nodes(nodes_df: pd.DataFrame, rels_df: pd.DataFrame, max_nodes_per_layer: int) -> list[dict[str, str]]:
    degrees = _degree_map(rels_df)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for index, row in nodes_df.iterrows():
        node_id = str(row.get("node_id", "")).strip()
        if not node_id:
            continue
        label = str(row.get("label", "")).strip()
        layer = TYPE_TO_LAYER.get(label, "Requirement")
        grouped[layer].append(
            {
                "node_id": node_id,
                "label": label,
                "name": str(row.get("name", node_id)).strip() or node_id,
                "description": str(row.get("description", "")).strip(),
                "degree": str(degrees.get(node_id, 0)),
                "index": str(index),
            }
        )

    selected: list[dict[str, str]] = []
    for layer in LAYER_ORDER:
        layer_nodes = sorted(
            grouped.get(layer, []),
            key=lambda item: (-int(item["degree"]), int(item["index"])),
        )
        limit = 1 if layer == "Product" else max_nodes_per_layer
        selected.extend(layer_nodes[:limit])
    return selected


def build_graph_html(nodes_df: pd.DataFrame, rels_df: pd.DataFrame, max_nodes_per_layer: int = 7) -> str:
    """Build a readable layered SVG preview for Neo4j node and relationship tables."""
    if nodes_df.empty or rels_df.empty or "node_id" not in nodes_df.columns:
        return ""

    nodes = _select_nodes(nodes_df, rels_df, max_nodes_per_layer)
    if not nodes:
        return ""

    layer_nodes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for node in nodes:
        layer_nodes[TYPE_TO_LAYER.get(node["label"], "Requirement")].append(node)

    width = 1220
    max_layer_count = max((len(layer_nodes.get(layer, [])) for layer in LAYER_ORDER), default=1)
    height = max(620, 210 + max_layer_count * 82)
    top = 152
    bottom = 70
    usable_height = height - top - bottom
    layer_x = {
        "Product": 105,
        "Evidence": 375,
        "Requirement": 615,
        "Function": 855,
        "Structure": 1095,
    }
    card_width = 170
    card_height = 58
    positions: dict[str, tuple[float, float]] = {}

    for layer in LAYER_ORDER:
        current_nodes = layer_nodes.get(layer, [])
        count = len(current_nodes)
        if not count:
            continue
        gap = usable_height / max(count - 1, 1)
        if count == 1:
            y_values = [top + usable_height / 2]
        else:
            y_values = [top + index * gap for index in range(count)]
        for node, y in zip(current_nodes, y_values):
            positions[node["node_id"]] = (layer_x[layer], y)

    rel_parts: list[str] = []
    for _, rel in rels_df.iterrows():
        source_id = str(rel.get("source_id", "")).strip()
        target_id = str(rel.get("target_id", "")).strip()
        if source_id not in positions or target_id not in positions:
            continue
        source_x, source_y = positions[source_id]
        target_x, target_y = positions[target_id]
        if source_x <= target_x:
            start_x = source_x + card_width / 2
            end_x = target_x - card_width / 2
        else:
            start_x = source_x - card_width / 2
            end_x = target_x + card_width / 2
        curve = max(abs(end_x - start_x) * 0.46, 56)
        control_1 = start_x + curve if source_x <= target_x else start_x - curve
        control_2 = end_x - curve if source_x <= target_x else end_x + curve
        rel_type = _safe(rel.get("type", ""))
        rel_parts.append(
            f'<path class="kg-edge" d="M {start_x:.1f} {source_y:.1f} C {control_1:.1f} {source_y:.1f}, '
            f'{control_2:.1f} {target_y:.1f}, {end_x:.1f} {target_y:.1f}" '
            f'marker-end="url(#arrow)"><title>{rel_type}</title></path>'
        )

    node_parts: list[str] = []
    for node in nodes:
        node_id = node["node_id"]
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        label = node["label"]
        color = TYPE_COLORS.get(label, "#64748B")
        label_name = TYPE_TITLES.get(label, label or "节点")
        name = _safe(_truncate(node["name"], 15))
        description = _safe(node["description"])
        full_title = _safe(f'{node["name"]} | {label_name} | {node["description"]}')
        node_parts.append(
            f'<g class="kg-node" transform="translate({x - card_width / 2:.1f},{y - card_height / 2:.1f})">'
            f'<title>{full_title}</title>'
            f'<rect class="node-label-bg" width="{card_width}" height="{card_height}" rx="17" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="22" cy="29" r="11" fill="{color}"/>'
            f'<text x="42" y="25" class="node-name">{name}</text>'
            f'<text x="42" y="43" class="node-type">{_safe(label_name)} · 关系 {node["degree"]}</text>'
            f'{f"<desc>{description}</desc>" if description else ""}'
            f'</g>'
        )

    header_parts = []
    for layer in LAYER_ORDER:
        x = layer_x[layer]
        header_parts.append(
            f'<g class="kg-layer-header">'
            f'<rect x="{x - card_width / 2:.1f}" y="88" width="{card_width}" height="34" rx="17" fill="#EEF5FF" stroke="#D7E6FF"/>'
            f'<text x="{x:.1f}" y="110" text-anchor="middle">{_safe(LAYER_TITLES[layer])}</text>'
            f'</g>'
        )

    legend_parts = []
    for label, color in TYPE_COLORS.items():
        legend_parts.append(
            f'<span><i style="background:{color}"></i>{_safe(TYPE_TITLES.get(label, label))}</span>'
        )

    return f"""
<div class="kg-layered-graph" role="img" aria-label="Neo4j 知识图谱分层关系预览">
  <style>
    .kg-layered-graph {{
      font-family: Arial, "Microsoft YaHei", "PingFang SC", sans-serif;
      background: linear-gradient(180deg, #F8FBFF 0%, #F4F7FB 100%);
      border: 1px solid #D8E2EC;
      border-radius: 18px;
      padding: 16px 18px 12px;
      color: #102033;
      box-sizing: border-box;
    }}
    .kg-title {{ font-size: 20px; font-weight: 800; margin-bottom: 4px; }}
    .kg-subtitle {{ color: #52657A; font-size: 13px; margin-bottom: 10px; }}
    .kg-legend {{ display: flex; flex-wrap: wrap; gap: 10px 16px; margin-bottom: 6px; color: #536579; font-size: 12px; }}
    .kg-legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
    .kg-legend i {{ width: 10px; height: 10px; border-radius: 999px; display: inline-block; }}
    .kg-edge {{ fill: none; stroke: #9FB0C2; stroke-width: 1.65; stroke-opacity: .42; pointer-events: stroke; }}
    .kg-node {{ filter: drop-shadow(0 8px 16px rgba(16, 32, 51, .08)); }}
    .node-name {{ font-size: 13px; font-weight: 800; fill: #102033; }}
    .node-type {{ font-size: 11px; fill: #5C6B7A; }}
    .kg-layer-header text {{ font-size: 13px; font-weight: 700; fill: #3C5974; }}
  </style>
  <div class="kg-title">知识图谱关系预览</div>
  <div class="kg-subtitle">关系路径：产品 → 需求 → 功能 → 结构；评论主题和关键词作为需求证据接入，标签采用白底卡片避免被颜色或连线遮挡。</div>
  <div class="kg-legend">{''.join(legend_parts)}</div>
  <svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMin meet">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#8FA1B4"></path>
      </marker>
    </defs>
    <rect x="18" y="70" width="{width - 36}" height="{height - 92}" rx="24" fill="#FFFFFF" opacity=".62"></rect>
    {''.join(header_parts)}
    {''.join(rel_parts)}
    {''.join(node_parts)}
  </svg>
</div>
"""
