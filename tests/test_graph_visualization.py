from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.graph_visualization import build_graph_html


class GraphVisualizationTests(unittest.TestCase):
    def test_graph_uses_readable_layered_layout(self) -> None:
        nodes_df = pd.DataFrame(
            [
                {"node_id": "PRODUCT_1", "label": "Product", "name": "马桶扶手", "description": "研究对象"},
                {"node_id": "TOPIC_0", "label": "Topic", "name": "主题0", "description": "安全 稳定"},
                {"node_id": "REQ_1", "label": "Requirement", "name": "安全稳定", "description": "用户痛点"},
                {"node_id": "FUNC_1", "label": "Function", "name": "防滑支撑功能", "description": "功能"},
                {"node_id": "STRU_1", "label": "Structure", "name": "U型扶手支撑结构", "description": "结构"},
                {"node_id": "KEY_1", "label": "Keyword", "name": "防滑", "description": "关键词"},
            ]
        )
        rels_df = pd.DataFrame(
            [
                {"source_id": "PRODUCT_1", "target_id": "REQ_1", "type": "HAS_REQUIREMENT"},
                {"source_id": "TOPIC_0", "target_id": "REQ_1", "type": "BELONGS_TO_TOPIC"},
                {"source_id": "REQ_1", "target_id": "FUNC_1", "type": "SATISFIED_BY"},
                {"source_id": "FUNC_1", "target_id": "STRU_1", "type": "REALIZED_BY"},
                {"source_id": "KEY_1", "target_id": "REQ_1", "type": "MENTIONS_KEYWORD"},
            ]
        )

        html = build_graph_html(nodes_df, rels_df)

        self.assertIn("kg-layered-graph", html)
        self.assertIn("关系路径：产品 → 需求 → 功能 → 结构", html)
        self.assertIn("node-label-bg", html)
        self.assertIn("<path", html)
        self.assertIn('marker-end="url(#arrow)"', html)
        self.assertIn("安全稳定", html)


if __name__ == "__main__":
    unittest.main()
