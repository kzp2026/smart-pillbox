from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.application.generation import ConfirmationRequired, GenerationCommand, GenerationService
from v2.providers.text import TextResult


class LiveTextProvider:
    def __init__(self) -> None:
        self.request = None

    def generate(self, request):
        self.request = request
        return TextResult("DeepSeek 增强后的完整设计方案", "live", "deepseek", "deepseek-chat")


class GenerationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = KnowledgeRepository(
            f"sqlite:///{Path(self.temp_dir.name) / 'v2.sqlite3'}", "private-owner"
        )
        self.repo.initialize()
        self.service = GenerationService(self.repo, confirmation_secret=b"test-confirmation-secret")
        self.command = GenerationCommand(
            target_product="智能药盒",
            demand_text="提醒老人按时吃药",
            provider="dashscope",
            model="wan2.7-image-pro",
            image_count=8,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_paid_images_require_exact_confirmation(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        with self.assertRaises(ConfirmationRequired):
            self.service.confirm_and_start(self.command, preview, provided_token="wrong")

    def test_valid_confirmation_creates_one_idempotent_run(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        first = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)
        second = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.repo.count_rows("pipeline_runs"), 1)

    def test_preview_exposes_model_count_and_no_secret(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        self.assertEqual(preview.provider, "dashscope")
        self.assertEqual(preview.model, "wan2.7-image-pro")
        self.assertEqual(preview.image_count, 8)
        self.assertNotIn("test-confirmation-secret", repr(preview))

    def test_design_generation_uses_private_evidence_and_persists_text_mode(self) -> None:
        raw_comment = "提醒声音太小，老人听不清"
        imported = self.repo.ingest_comments(
            "智能药盒", "适老健康", "comments.csv", [raw_comment]
        )
        self.repo.add_requirement_once(
            imported.product_id,
            imported.batch_id,
            "提醒反馈",
            "提醒要明显",
            ["提醒"],
            "提醒声音太小，老人听不清",
            80,
        )
        preview = self.service.preview(self.command, nonce="design-run")
        run = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)

        generated = self.service.generate_design(run.id, self.command, {}, LiveTextProvider())

        self.assertEqual(generated.package["design_text"], "DeepSeek 增强后的完整设计方案")
        self.assertEqual(generated.package["text_generation_mode"], "live")
        self.assertGreater(generated.context["evidence_count"], 0)
        graph = generated.package["requirement_function_structure_graph"]
        self.assertTrue(graph["requirements"])
        self.assertTrue(graph["functions"])
        self.assertTrue(graph["structures"])
        self.assertTrue(graph["links"])
        visual_gate = generated.package["visual_quality_gate"]
        self.assertEqual(visual_gate["status"], "pass")
        self.assertEqual(visual_gate["planned_asset_count"], 8)
        visual_assets = generated.package["visual_assets"]
        self.assertEqual(len({item["canonical_product_id"] for item in visual_assets}), 1)
        self.assertIn("assembly sequence", next(
            item["prompt"] for item in visual_assets if item["key"] == "exploded"
        ).lower())
        self.assertIsNotNone(self.repo.get_generation_run(run.id))
        self.assertNotIn(raw_comment, generated.package["industrial_design_prompt"])
        self.assertTrue(all(raw_comment not in prompt for prompt in generated.package["image_prompts"]))

    def test_design_generation_uses_a_bounded_traceable_text_input(self) -> None:
        imported = self.repo.ingest_comments(
            "智能药盒", "适老健康", "comments.csv", ["提醒" + "很长的历史评论" * 4000]
        )
        self.repo.add_requirement_once(
            imported.product_id,
            imported.batch_id,
            "提醒反馈",
            "提醒需求" + "冗长元数据" * 4000,
            ["提醒"],
            "提醒声音太小",
            80,
        )
        preview = self.service.preview(self.command, nonce="bounded-input")
        run = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)
        provider = LiveTextProvider()

        generated = self.service.generate_design(run.id, self.command, {}, provider)

        self.assertLessEqual(len(provider.request.user_prompt), 12_000)
        self.assertIn('"评论编号"', provider.request.user_prompt)
        self.assertIn('"需求编号"', provider.request.user_prompt)
        self.assertNotIn("很长的历史评论", provider.request.user_prompt)
        self.assertNotIn("冗长元数据" * 100, provider.request.user_prompt)
        self.assertEqual(generated.context["text_input_budget"]["max_characters"], 12_000)
        self.assertLessEqual(generated.context["text_input_budget"]["actual_characters"], 12_000)

    def test_researcher_confirmed_paths_are_traced_in_the_prompt(self) -> None:
        imported = self.repo.ingest_comments(
            "智能药盒", "适老健康", "comments.csv", ["提醒声音太小，老人听不清"]
        )
        requirement_id = self.repo.add_requirement_once(
            imported.product_id, imported.batch_id, "提醒反馈", "提醒要明显", ["提醒"],
            "提醒声音太小，老人听不清", 80,
        )
        preview = self.service.preview(self.command, nonce="researcher-confirmed")
        run = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)
        provider = LiveTextProvider()
        graph = {
            "version": "rfs-candidate-v2", "review_status": "研究者已确认",
            "evidence_status": "研究者确认关系证据", "approved_mapping_count": 1,
            "researcher_confirmed_mapping_count": 1,
            "used_graph_paths": [{
                "path_id": "S23-001", "mapping_id": "S23-RFS-001", "requirement_id": requirement_id,
                "comment_ids": ["C1"], "review_decision": "研究者已确认", "reviewer": "", "reviewed_at": "",
            }],
            "requirements": [{"name": "提醒反馈", "detail": "提醒声音太小"}],
            "functions": [{"name": "多模态提醒", "source": "映射审核表"}],
            "structures": [{"name": "扬声器与LED", "source": "映射审核表"}],
            "links": [{
                "mapping_id": "S23-RFS-001", "requirement": "提醒反馈", "function": "多模态提醒",
                "structure": "扬声器与LED", "evidence": "C1", "comment_ids": ["C1"],
                "review_status": "研究者已确认",
            }],
        }

        generated = self.service.generate_design(run.id, self.command, {}, provider, graph)

        self.assertEqual(generated.context["used_graph_paths"][0]["mapping_id"], "S23-RFS-001")
        self.assertIn('"图谱状态":"研究者确认关系证据"', provider.request.user_prompt)
        self.assertIn('"映射编号":"S23-RFS-001"', provider.request.user_prompt)
        self.assertIn('"评论证据编号":["C1"]', provider.request.user_prompt)

    def test_graph_snapshot_deduplicates_requirements_and_maps_specific_functions(self) -> None:
        graph = GenerationService._build_graph_snapshot(
            "为适老智能药盒优化提醒、收纳与外观体验。",
            {
                "requirements": [
                    {"title": "提醒反馈", "description": "提醒声音太小，老人听不清。"},
                    {"title": "提醒反馈", "description": "希望能看到服药确认状态。"},
                    {"title": "容量收纳", "description": "药仓需要按时段清晰分格。"},
                    {"title": "外观质感", "description": "希望产品更简洁、有品质感。"},
                ]
            },
            {},
        )

        self.assertEqual(
            [item["name"] for item in graph["requirements"]],
            ["提醒反馈", "容量收纳", "外观质感"],
        )
        mapped = {item["requirement"]: item for item in graph["links"]}
        self.assertIn("提醒", mapped["提醒反馈"]["function"])
        self.assertIn("扬声器", mapped["提醒反馈"]["structure"])
        self.assertIn("分格", mapped["容量收纳"]["function"])
        self.assertIn("分格", mapped["容量收纳"]["structure"])
        self.assertIn("形态", mapped["外观质感"]["function"])
        self.assertIn("壳体", mapped["外观质感"]["structure"])


if __name__ == "__main__":
    unittest.main()
