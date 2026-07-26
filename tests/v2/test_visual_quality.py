from __future__ import annotations

import unittest


class VisualQualityTests(unittest.TestCase):
    def test_complete_delivery_plan_has_asset_specific_acceptance_contracts(self) -> None:
        from v2.application.visual_quality import qualify_visual_delivery

        assets, gate = qualify_visual_delivery(
            "Smart pillbox",
            [
                {"key": "render_1", "label": "Product render 1", "prompt": "hero"},
                {"key": "render_2", "label": "Product render 2", "prompt": "second hero"},
                {"key": "exploded", "label": "Exploded view", "prompt": "exploded"},
                {"key": "detail", "label": "Detail", "prompt": "detail"},
                {"key": "three_view", "label": "Three view", "prompt": "three view"},
                {"key": "board", "label": "Design board", "prompt": "board"},
                {"key": "usage_1", "label": "Usage 1", "prompt": "usage"},
                {"key": "usage_2", "label": "Usage 2", "prompt": "usage"},
            ],
            {
                "structure": "transparent hinged lid, six removable pill compartments, front display",
                "materials": "food-safe ABS, clear PC, silicone seal",
                "colors": "warm white body, low-saturation blue accent",
                "dimensions": "compact tabletop size for one-hand operation",
                "core_functions": "scheduled reminder, compartment storage, status feedback",
                "target_users": "older adults and family caregivers",
                "forbidden_changes": "do not change the compartment count or the front interaction zone",
            },
        )

        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["planned_asset_count"], 8)
        self.assertEqual(gate["missing_requirements"], [])
        by_key = {asset["key"]: asset for asset in assets}
        self.assertEqual(len({asset["canonical_product_id"] for asset in assets}), 1)
        self.assertIn("assembly sequence", by_key["exploded"]["prompt"].lower())
        self.assertIn("no duplicate shells", by_key["exploded"]["prompt"].lower())
        self.assertIn("orthographic", by_key["three_view"]["prompt"].lower())
        self.assertIn("same scale", by_key["three_view"]["prompt"].lower())
        self.assertIn("cmf", by_key["board"]["prompt"].lower())
        self.assertIn("no illegible paragraphs", by_key["board"]["prompt"].lower())
        self.assertIn("complete fingers", by_key["usage_1"]["prompt"].lower())
        self.assertIn("complete fingers", by_key["usage_2"]["prompt"].lower())
        self.assertGreaterEqual(len(by_key["detail"]["acceptance_criteria"]), 4)

    def test_quality_gate_reports_missing_asset_instead_of_claiming_pass(self) -> None:
        from v2.application.visual_quality import qualify_visual_delivery

        _assets, gate = qualify_visual_delivery(
            "Smart pillbox",
            [{"key": "render_1", "label": "Product render 1", "prompt": "hero"}],
            {},
        )

        self.assertEqual(gate["status"], "needs_revision")
        self.assertIn("usage_2", gate["missing_requirements"])


if __name__ == "__main__":
    unittest.main()
