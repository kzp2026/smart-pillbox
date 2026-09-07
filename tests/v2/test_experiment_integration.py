from __future__ import annotations

import copy
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.experiment import ExperimentService, load_example_config
from v2.application.generation import GenerationCommand, GenerationService
from v2.application.imports import ImportService


class CapturingProvider:
    def __init__(self):
        self.request = None

    def generate(self, request):
        from v2.providers.text import TextResult
        self.request = request
        return TextResult("方案", "fake", "fake", "fake-design-v1")


class ExperimentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "owner")
        self.repo.initialize()
        self.store = LocalArtifactStore(root / "store")

    def tearDown(self):
        self.temp.cleanup()

    def test_import_and_graph_share_the_versioned_semantics(self):
        result = ImportService(self.repo).import_comments(
            "药盒", "健康", "comments.csv", ["希望药盒有儿童锁，避免误服"]
        )
        self.assertEqual(result.new_requirement_count, 1)
        context = self.repo.search_context("药盒 儿童锁", limit=8)
        graph = GenerationService.build_graph_snapshot("", context, {})
        self.assertEqual(graph["version"], "rfs-candidate-v2")
        self.assertEqual(graph["review_status"], "pending_review")
        self.assertIn("锁扣", graph["structures"][0]["name"])

    def test_design_prompt_contains_reviewed_graph_and_honest_status(self):
        service = GenerationService(self.repo, b"0123456789abcdef")
        command = GenerationCommand("药盒", "提醒老人按时服药", "fake", "fake-design-v1", 0)
        preview = service.preview(command, "n")
        run = service.confirm_and_start(command, preview, None)
        provider = CapturingProvider()
        generated = service.generate_design(run.id, command, {}, provider)
        self.assertIn("候选设计推导（无正式图谱证据）", provider.request.user_prompt)
        self.assertEqual(generated.context["approved_mapping_count"], 0)
        self.assertEqual(generated.context["used_graph_paths"], [])
        self.assertFalse(generated.context["independent_evaluation_completed"])
        self.assertFalse(generated.context["closed_loop_validated"])
        self.assertEqual(generated.package["generation_mode"], "fake")
        self.assertEqual(generated.package["text_generation_prompt"]["user_prompt"], provider.request.user_prompt)

    def test_unmatched_import_does_not_create_scored_fake_requirement(self):
        result = ImportService(self.repo).import_comments("药盒", "健康", "comments.csv", ["今天收到包裹"])
        self.assertEqual(result.new_requirement_count, 0)

    def test_failed_experiment_leaves_private_failed_run(self):
        root = Path(self.temp.name)
        source = root / "bad.csv"
        source.write_text("错误列\n内容", encoding="utf-8-sig")
        config = copy.deepcopy(load_example_config())
        config["product_name"] = "失败实验"
        with self.assertRaises(ValueError):
            ExperimentService(self.repo, self.store).run(config, source)
        run = self.repo.list_pipeline_runs(10, target_product="失败实验", provider="research")[0]
        self.assertEqual(run.status.value, "failed")
        self.assertNotIn("错误列", self.repo.get_pipeline_run(run.id).current_stage)
        self.assertGreater(len(ExperimentService(self.repo, self.store).download(run.id)), 0)

    def test_request_id_is_idempotent_but_new_request_starts_new_run(self):
        root = Path(self.temp.name)
        source = root / "comments.csv"
        source.write_text("评论\n提醒声音太小", encoding="utf-8-sig")
        config = copy.deepcopy(load_example_config())
        config["product_name"] = "请求隔离"
        config["topic"]["n_topics"] = 1
        first = ExperimentService(self.repo, self.store).run(
            config, source, request_id="request-one", stop_after="graph"
        )
        repeated = ExperimentService(self.repo, self.store).run(
            config, source, request_id="request-one", stop_after="graph"
        )
        second = ExperimentService(self.repo, self.store).run(
            config, source, request_id="request-two", stop_after="graph"
        )
        self.assertEqual(first["pipeline_run_id"], repeated["pipeline_run_id"])
        self.assertNotEqual(first["pipeline_run_id"], second["pipeline_run_id"])
        archive=ExperimentService(self.repo,self.store).download(first['pipeline_run_id'])
        with zipfile.ZipFile(io.BytesIO(archive)) as saved:
            self.assertIn('review_materials/01_initial_free_annotation.xlsx',saved.namelist())
            manifest=json.loads(saved.read('run_manifest.json'))
            self.assertTrue(manifest['supplemental_artifacts'])
        config['product_name']='另一个独立产品'
        different_product=ExperimentService(self.repo,self.store).run(config,source,request_id='request-one',stop_after='graph')
        self.assertNotEqual(first['pipeline_run_id'],different_product['pipeline_run_id'])
        self.assertEqual(different_product['product'],'另一个独立产品')
        self.assertEqual(first["run_status"], "paused")
        self.assertEqual(first["stopped_after"], "graph")
        self.assertGreater(len(ExperimentService(self.repo, self.store).download(first["pipeline_run_id"])), 0)

    def test_service_exposes_v2_change_child_entry(self):
        service = ExperimentService(self.repo, self.store)
        self.assertTrue(callable(service.rerun_with_changes))

    def test_runner_is_archived_privately_and_can_be_reopened(self):
        root = Path(self.temp.name)
        source = root / "comments.csv"
        with source.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["评论", "评分", "日期", "产品"])
            writer.writeheader()
            writer.writerow({"评论": "提醒声音太小", "评分": "2", "日期": "2026-01-01", "产品": "药盒"})
        config = copy.deepcopy(load_example_config())
        config["product_name"] = "药盒"
        config["topic"]["n_topics"] = 1
        config["generation"]["repetitions"] = 1
        saved = ExperimentService(self.repo, self.store).run(config, source)
        self.assertEqual(saved["provider"], "research")
        self.assertEqual(saved["model"], "paper-repro-v2.1")
        self.assertEqual(saved["approved_mapping_count"], 0)
        self.assertFalse(saved["independent_evaluation_completed"])
        reopened = ExperimentService(self.repo, self.store).load(saved["pipeline_run_id"])
        self.assertEqual(reopened["manifest"]["method_version"], "paper-repro-v2.1")
        archive_bytes = ExperimentService(self.repo, self.store).download(saved["pipeline_run_id"])
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archived:
            manifest = json.loads(archived.read("run_manifest.json"))
        self.assertEqual(manifest["status"], "completed")


if __name__ == "__main__":
    unittest.main()
