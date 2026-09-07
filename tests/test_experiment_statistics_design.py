import unittest

from experiment.evaluation.statistics import DIMENSIONS, compare_versions, summarize_reviews


def review(reviewer, scheme, score):
    row = {
        "reviewer_id": reviewer,
        "background": "工业设计",
        "scheme_id": scheme,
        "evaluated_at": "2026-09-05T12:00:00+08:00",
        "strengths": "清晰",
        "issues": "待验证",
        "suggestions": "继续验证",
    }
    row.update({dimension: score for dimension in DIMENSIONS})
    return row


def confirmatory_design(**updates):
    design = {
        "inference_requested": True,
        "primary_metric": "需求匹配度",
        "specified_before_outcome_review": True,
        "analysis_unit": "independent_scheme_pair",
        "pairing": "same_reviewer_within_scheme_pair",
        "alternative": "two-sided",
        "alpha": 0.05,
        "multiplicity": "holm",
        "missing_data": "complete_pair_only",
        "require_same_reviewer_set": True,
        "independent_pairs_assumed": True,
        "symmetric_difference_distribution_assumed": True,
        "sample_size_justification": "由研究方案预先确定；不以观察到的 p 值或固定 5 对门槛决定。",
        "registration_status": "pre_specified_not_registered",
    }
    design.update(updates)
    return design


class StatisticsDesignTests(unittest.TestCase):
    def test_summary_distinguishes_unique_schemes_from_review_rows(self):
        rows = [review("R1", "A", 3), review("R2", "A", 4), review("R1", "B", 2)]
        result = summarize_reviews(rows)
        self.assertEqual(3, result["n_review_rows"])
        self.assertEqual(2, result["n_unique_schemes"])
        self.assertEqual("descriptive_only", result["inference"]["status"])

    def test_default_never_enables_significance_even_with_many_pairs(self):
        rows, pairs = [], []
        for number in range(1, 8):
            v1, v2 = f"A{number}", f"B{number}"
            pairs.append({"pair_id": f"P{number}", "v1_scheme_id": v1, "v2_scheme_id": v2})
            rows.extend([review("R1", v1, 1), review("R1", v2, 5)])
        result = compare_versions(rows, pairs)
        self.assertEqual(7, result["n_independent_pairs"])
        self.assertEqual(14, result["n_unique_schemes"])
        self.assertEqual(14, result["n_review_rows"])
        self.assertFalse(result["can_claim_significance"])
        self.assertFalse(result["can_claim_real_improvement"])
        self.assertEqual("design_not_supplied", result["inference"]["status"])
        self.assertEqual("exploratory_only", result["p_value_role"])
        self.assertTrue(all(metric["p_value_role"] == "exploratory_only" for metric in result["dimensions"].values()))
        self.assertTrue(all(not metric["significant"] for metric in result["dimensions"].values()))

    def test_explicit_design_only_makes_prespecified_primary_metric_eligible(self):
        rows, pairs = [], []
        for number in range(1, 9):
            v1, v2 = f"A{number}", f"B{number}"
            pairs.append({"pair_id": f"P{number}", "v1_scheme_id": v1, "v2_scheme_id": v2})
            rows.extend([review("R1", v1, 1), review("R1", v2, 5)])
        result = compare_versions(rows, pairs, design=confirmatory_design())
        self.assertEqual("eligible", result["inference"]["status"])
        self.assertTrue(result["dimensions"]["需求匹配度"]["inferentially_eligible"])
        self.assertEqual("confirmatory_primary", result["dimensions"]["需求匹配度"]["p_value_role"])
        self.assertTrue(result["dimensions"]["需求匹配度"]["significant"])
        self.assertTrue(result["can_claim_significance"])
        self.assertFalse(result["dimensions"]["创新性"]["inferentially_eligible"])
        self.assertEqual("secondary_exploratory", result["dimensions"]["创新性"]["inference_status"])
        self.assertEqual("exploratory_secondary", result["dimensions"]["创新性"]["p_value_role"])
        self.assertFalse(result["can_claim_real_improvement"])

    def test_mismatched_reviewers_and_incomplete_pairs_are_reported_and_block_inference(self):
        pairs = [
            {"pair_id": "P1", "v1_scheme_id": "A1", "v2_scheme_id": "B1"},
            {"pair_id": "P2", "v1_scheme_id": "A2", "v2_scheme_id": "B2"},
        ]
        rows = [
            review("R1", "A1", 2), review("R1", "B1", 4), review("R2", "A1", 2),
            review("R1", "A2", 2),
        ]
        result = compare_versions(rows, pairs, design=confirmatory_design())
        self.assertEqual("ineligible", result["inference"]["status"])
        self.assertEqual(["P1"], result["reviewer_set_mismatch_pair_ids"])
        self.assertEqual(["P2"], result["incomplete_pair_ids"])
        self.assertEqual(1, result["n_independent_pairs"])
        self.assertFalse(result["can_claim_significance"])

    def test_design_cannot_relabel_posthoc_or_unjustified_analysis_as_confirmatory(self):
        rows = [review("R1", "A", 2), review("R1", "B", 4)]
        pairs = [{"pair_id": "P1", "v1_scheme_id": "A", "v2_scheme_id": "B"}]
        for update in (
            {"specified_before_outcome_review": False},
            {"primary_metric": "创新性"},
            {"alpha": 0.10},
            {"registration_status": "registered"},
            {"sample_size_justification": ""},
            {"symmetric_difference_distribution_assumed": False},
        ):
            with self.subTest(update=update):
                result = compare_versions(rows, pairs, design=confirmatory_design(**update))
                self.assertEqual("ineligible", result["inference"]["status"])
                self.assertFalse(result["can_claim_significance"])


if __name__ == "__main__":
    unittest.main()
