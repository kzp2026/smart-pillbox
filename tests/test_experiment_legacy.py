import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class LegacyResearchTests(unittest.TestCase):
    def test_no_silent_fallback_in_legacy_clustering(self):
        source=(ROOT/'scripts/04_bertopic_clustering.py').read_text(encoding='utf-8')
        self.assertNotIn('pure_python_kmeans',source)
        self.assertNotIn('if result is None',source)
        self.assertIn('experiment.pipeline.topics',source)

    def test_legacy_mapping_uses_authoritative_semantics(self):
        source=(ROOT/'scripts/05_build_mapping_database.py').read_text(encoding='utf-8')
        self.assertIn('experiment.pipeline.semantics',source)
        self.assertNotIn('resolve_latest_output_path',source)

    def test_legacy_paper_entry_delegates_to_shared_runner(self):
        self.assertTrue((ROOT/'scripts/run_paper_experiment.py').exists())

    def test_shared_product_generator_does_not_claim_quality(self):
        from scripts.product_knowledge_base import generate_design_package
        result=generate_design_package('药盒','提醒并简化老人操作',{'products':[],'requirements':[],'comments':[],'evidence_count':0})
        self.assertEqual(result['quality_score'],0)
        self.assertEqual(result['quality_status'],'材料完整度检查（非方案质量）')
        self.assertIn('completeness_checks',result)


if __name__=='__main__':unittest.main()
