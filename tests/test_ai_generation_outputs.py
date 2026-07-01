from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)


def build_sample_mapping_outputs(output_dir: Path, product_name: str = "马桶扶手") -> None:
    write_workbook(
        output_dir / f"{product_name}_需求功能映射数据库.xlsx",
        {
            "用户需求表": pd.DataFrame(
                [
                    {
                        "req_id": "REQ_SAFE",
                        "需求名称": "安全稳定",
                        "需求类别": "安全稳定",
                        "来源关键词": "安全、稳定",
                        "需求描述": "用户需要起身和坐下时更稳定的支撑。",
                        "情感倾向": "痛点优先",
                        "重要度": 12.5,
                        "负向评论数": 3,
                        "正向评论数": 1,
                    }
                ]
            ),
            "产品功能表": pd.DataFrame(
                [
                    {
                        "func_id": "FUNC_GRIP",
                        "功能名称": "防滑支撑功能",
                        "功能类别": "安全稳定",
                        "功能描述": "提供起身、落座过程中的稳定抓握和支撑。",
                        "设计目标": "提升老人如厕时的安全感。",
                        "优先级": 1,
                    }
                ]
            ),
            "产品结构表": pd.DataFrame(
                [
                    {
                        "structure_id": "STRU_ARM",
                        "结构名称": "U型扶手支撑结构",
                        "结构类型": "安全稳定",
                        "结构描述": "采用双侧支撑和防滑握把形成稳定受力结构。",
                    }
                ]
            ),
            "需求功能映射": pd.DataFrame(
                [{"req_id": "REQ_SAFE", "func_id": "FUNC_GRIP", "映射理由": "安全稳定可通过防滑支撑功能实现。", "映射强度": 12.5}]
            ),
            "功能结构映射": pd.DataFrame(
                [{"func_id": "FUNC_GRIP", "structure_id": "STRU_ARM", "映射理由": "防滑支撑功能依赖U型扶手支撑结构。"}]
            ),
            "主题需求映射": pd.DataFrame(
                [{"topic_id": 0, "主题关键词": "安全 稳定 老人 起身", "req_id": "REQ_SAFE", "需求名称": "安全稳定", "映射依据": "主题关键词命中需求规则"}]
            ),
            "设计机会点": pd.DataFrame(
                [{"设计机会点": "安全稳定", "证据关键词": "安全、稳定", "建议功能": "防滑支撑功能", "建议结构": "U型扶手支撑结构", "论文实验解释": "由评论推导。"}]
            ),
        },
    )
    write_workbook(
        output_dir / "BERTopic主题聚类结果.xlsx",
        {
            "主题汇总": pd.DataFrame(
                [
                    {
                        "topic_id": 0,
                        "主题名称": "安全稳定主题",
                        "评论数": 8,
                        "占比": 0.4,
                        "主题关键词": "安全 稳定 老人 起身",
                        "代表性评论": "老人起身时不稳，希望扶手更牢固。 | 坐下时需要防滑支撑。",
                        "algorithm": "test",
                    }
                ]
            ),
            "评论主题聚类结果": pd.DataFrame(
                [
                    {"topic_id": 0, "comment_original": "老人起身时不稳，希望扶手更牢固。", "clean_comment": "老人 起身 不稳 扶手 牢固"},
                    {"topic_id": 0, "comment_original": "坐下时需要防滑支撑。", "clean_comment": "坐下 需要 防滑 支撑"},
                ]
            ),
        },
    )
    write_workbook(
        output_dir / "情感分析结果.xlsx",
        {
            "情感示例评论": pd.DataFrame(
                [{"关键词": "安全", "示例评论1": "老人起身时不稳，希望扶手更牢固。", "示例评论2": "坐下时需要防滑支撑。"}]
            )
        },
    )
    pd.DataFrame(
        [
            {"node_id": f"PRODUCT_{product_name}", "label": "Product", "name": product_name, "category": "研究对象", "description": "", "source": "", "weight": 1},
            {"node_id": "REQ_SAFE", "label": "Requirement", "name": "安全稳定", "category": "安全稳定", "description": "", "source": "安全、稳定", "weight": 12.5},
            {"node_id": "FUNC_GRIP", "label": "Function", "name": "防滑支撑功能", "category": "安全稳定", "description": "", "source": "", "weight": 1},
            {"node_id": "STRU_ARM", "label": "Structure", "name": "U型扶手支撑结构", "category": "安全稳定", "description": "", "source": "", "weight": 1},
        ]
    ).to_csv(output_dir / "neo4j_nodes.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {"source_id": f"PRODUCT_{product_name}", "target_id": "REQ_SAFE", "type": "HAS_REQUIREMENT", "weight": 12.5, "reason": "产品包含需求"},
            {"source_id": "REQ_SAFE", "target_id": "FUNC_GRIP", "type": "SATISFIED_BY", "weight": 12.5, "reason": "需求由功能满足"},
            {"source_id": "FUNC_GRIP", "target_id": "STRU_ARM", "type": "REALIZED_BY", "weight": 1, "reason": "功能由结构实现"},
        ]
    ).to_csv(output_dir / "neo4j_relationships.csv", index=False, encoding="utf-8-sig")


def run_script(script_name: str, output_dir: Path, product_name: str = "马桶扶手") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "scripts" / script_name),
            "--output-dir",
            str(output_dir),
            "--product-name",
            product_name,
        ],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
    )


class AIGenerationOutputTests(unittest.TestCase):
    def test_ai_generation_parameter_exports_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            build_sample_mapping_outputs(output_dir)

            result = run_script("07_generate_ai_parameters.py", output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            mapping_path = output_dir / "需求—功能—结构映射表.xlsx"
            ai_table_path = output_dir / "AI生成参数表.xlsx"
            json_path = output_dir / "ai_generation_parameters.json"
            prompt_path = output_dir / "prompt_template.txt"
            self.assertTrue(mapping_path.exists())
            self.assertTrue(ai_table_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(prompt_path.exists())

            mapping_df = pd.read_excel(mapping_path)
            self.assertEqual(
                list(mapping_df.columns),
                [
                    "需求主题",
                    "用户痛点",
                    "知识图谱路径",
                    "功能参数",
                    "结构参数",
                    "材料参数",
                    "场景参数",
                    "AI文本生成参数",
                    "AI图像生成参数",
                    "评价指标",
                ],
            )
            self.assertIn("马桶扶手 → 安全稳定 → 防滑支撑功能 → U型扶手支撑结构", mapping_df.loc[0, "知识图谱路径"])

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["product_type"], "马桶扶手")
            self.assertIn("安全稳定", payload["core_needs"])
            first_item = payload["generation_parameters"][0]
            for key in [
                "need",
                "pain_point",
                "function_parameter",
                "structure_parameter",
                "material_parameter",
                "scene_parameter",
                "text_prompt_parameter",
                "image_prompt_parameter",
            ]:
                self.assertTrue(first_item[key])

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("产品类型：{product_type}", prompt)
            self.assertIn("输出内容", prompt)
            self.assertIn("产品定位", prompt)

    def test_design_evaluation_exports_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            build_sample_mapping_outputs(output_dir)
            ai_result = run_script("07_generate_ai_parameters.py", output_dir)
            self.assertEqual(ai_result.returncode, 0, ai_result.stderr)
            (output_dir / "马桶扶手产品设计方案.txt").write_text("马桶扶手设计方案：强化防滑支撑、适老化握持与安全安装。", encoding="utf-8")

            result = run_script("09_evaluate_design_scheme.py", output_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            evaluation_path = output_dir / "方案评价表.xlsx"
            summary_path = output_dir / "开题报告实验结果摘要.docx"
            optimization_prompt_path = output_dir / "方案优化建议.txt"
            optimized_parameters_path = output_dir / "优化后AI生成参数.json"
            self.assertTrue(evaluation_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(optimization_prompt_path.exists())
            self.assertTrue(optimized_parameters_path.exists())
            evaluation_df = pd.read_excel(evaluation_path)
            self.assertEqual(list(evaluation_df.columns), ["评价指标", "分值", "评价说明", "优化建议"])
            self.assertEqual(
                evaluation_df["评价指标"].tolist(),
                [
                    "需求匹配度",
                    "适老化友好性",
                    "功能完整性",
                    "结构合理性",
                    "操作便利性",
                    "材料可行性",
                    "工程可行性",
                    "成本合理性",
                    "可优化性",
                ],
            )
            self.assertIn("生成—评价—优化", optimization_prompt_path.read_text(encoding="utf-8"))
            optimized_payload = json.loads(optimized_parameters_path.read_text(encoding="utf-8"))
            self.assertEqual(optimized_payload["product_type"], "马桶扶手")
            self.assertTrue(optimized_payload["optimization_focus"])


if __name__ == "__main__":
    unittest.main()
