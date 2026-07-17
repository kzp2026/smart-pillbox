from __future__ import annotations

import unittest

from v2.pipeline.catalog import LEGACY_STAGES, V2_STAGES


class PipelineCatalogTests(unittest.TestCase):
    def test_every_legacy_stage_is_mapped_exactly_once(self) -> None:
        mapped = [legacy for group in V2_STAGES for legacy in group.legacy_stage_ids]

        self.assertEqual(sorted(mapped), [f"{index:02d}" for index in range(1, 11)])
        self.assertEqual(len(mapped), len(set(mapped)))

    def test_catalog_preserves_all_original_scripts_and_outputs(self) -> None:
        self.assertEqual(len(LEGACY_STAGES), 10)
        self.assertEqual(LEGACY_STAGES[0].script_name, "01_clean_comments.py")
        self.assertEqual(LEGACY_STAGES[-1].script_name, "09_evaluate_design_scheme.py")
        self.assertIn("设计展板", LEGACY_STAGES[8].output_pattern)
        self.assertIn("方案评价表", LEGACY_STAGES[9].output_pattern)


if __name__ == "__main__":
    unittest.main()
