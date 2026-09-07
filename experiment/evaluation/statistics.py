import math
import re
from datetime import datetime
from statistics import mean, median, stdev

from scipy.stats import rankdata, t, wilcoxon


DIMENSIONS = [
    "需求匹配度", "适老化友好性", "功能完整性", "操作便利性",
    "结构合理性", "工程可行性", "创新性",
]
PRIMARY_METRIC = "需求匹配度"
TEXT_FIELDS = ["reviewer_id", "background", "scheme_id", "evaluated_at", "strengths", "issues", "suggestions"]
_ANON_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
def validate_reviews(rows, scheme_ids) -> list[dict]:
    allowed = set(scheme_ids)
    seen = set()
    clean = []
    for index, source in enumerate(rows, 1):
        missing = [field for field in TEXT_FIELDS + DIMENSIONS if field not in source]
        if missing:
            raise ValueError(f"row {index}: missing fields {missing}")
        row = dict(source)
        for field in TEXT_FIELDS:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"row {index}: invalid {field}")
            row[field] = row[field].strip()
        if not _ANON_ID.fullmatch(row["reviewer_id"]) or not _ANON_ID.fullmatch(row["scheme_id"]):
            raise ValueError(f"row {index}: IDs must be anonymous coded IDs")
        if row["scheme_id"] not in allowed:
            raise ValueError(f"row {index}: unknown scheme")
        try:
            datetime.fromisoformat(row["evaluated_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"row {index}: evaluated_at must be ISO 8601") from exc
        key = (row["reviewer_id"], row["scheme_id"])
        if key in seen:
            raise ValueError(f"row {index}: duplicate reviewer and scheme")
        seen.add(key)
        for dimension in DIMENSIONS:
            value = row[dimension]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise ValueError(f"row {index}: {dimension} must be integer 1-5")
        clean.append(row)
    return clean


def _describe(values):
    n = len(values)
    avg = mean(values)
    sd = stdev(values) if n > 1 else None
    ci = None if n < 2 else [avg - t.ppf(0.975, n - 1) * sd / math.sqrt(n), avg + t.ppf(0.975, n - 1) * sd / math.sqrt(n)]
    return {"n": n, "mean": avg, "sample_std": sd, "median": median(values), "ci95": ci}


def _icc_2_1(rows):
    reviewers = sorted({row["reviewer_id"] for row in rows})
    schemes = sorted({row["scheme_id"] for row in rows})
    lookup = {(row["reviewer_id"], row["scheme_id"]): mean(row[d] for d in DIMENSIONS) for row in rows}
    if len(reviewers) < 2 or len(schemes) < 2 or len(lookup) != len(reviewers) * len(schemes):
        return {"status": "insufficient_complete_crossed_design", "value": None}
    n, k = len(schemes), len(reviewers)
    grand = mean(lookup.values())
    scheme_means = {s: mean(lookup[(r, s)] for r in reviewers) for s in schemes}
    reviewer_means = {r: mean(lookup[(r, s)] for s in schemes) for r in reviewers}
    ms_scheme = k * sum((v - grand) ** 2 for v in scheme_means.values()) / (n - 1)
    ms_reviewer = n * sum((v - grand) ** 2 for v in reviewer_means.values()) / (k - 1)
    residual = sum((lookup[(r, s)] - scheme_means[s] - reviewer_means[r] + grand) ** 2 for r in reviewers for s in schemes)
    ms_error = residual / ((n - 1) * (k - 1))
    denominator = ms_scheme + (k - 1) * ms_error + k * (ms_reviewer - ms_error) / n
    value = None if denominator == 0 else (ms_scheme - ms_error) / denominator
    return {"status": "ok", "value": value, "n_schemes": n, "n_reviewers": k}


def summarize_reviews(rows, *, simulated=False) -> dict:
    if not rows:
        return {"simulated": simulated, "schemes": {}, "n_review_rows": 0, "n_unique_schemes": 0, "icc_2_1": {"status": "insufficient_complete_crossed_design", "value": None}, "inference": {"status": "descriptive_only", "reason": "summaries_do_not_test_hypotheses"}, "can_claim_significance": False}
    rows = validate_reviews(rows, {row.get("scheme_id") for row in rows})
    schemes = {}
    for scheme in sorted({row["scheme_id"] for row in rows}):
        selected = [row for row in rows if row["scheme_id"] == scheme]
        schemes[scheme] = {"dimensions": {dimension: _describe([row[dimension] for row in selected]) for dimension in DIMENSIONS}}
    return {"simulated": simulated, "schemes": schemes, "n_review_rows": len(rows), "n_unique_schemes": len(schemes), "icc_2_1": _icc_2_1(rows), "inference": {"status": "descriptive_only", "reason": "summaries_do_not_test_hypotheses"}, "can_claim_significance": False}


def _wilcoxon(differences):
    nonzero = [value for value in differences if value != 0]
    if not nonzero:
        return {"statistic": 0.0, "p_value": 1.0, "matched_rank_biserial": 0.0, "n_nonzero": 0}
    ranks = rankdata([abs(value) for value in nonzero], method="average")
    positive = sum(rank for rank, value in zip(ranks, nonzero) if value > 0)
    negative = sum(rank for rank, value in zip(ranks, nonzero) if value < 0)
    tested = wilcoxon(nonzero, zero_method="wilcox", alternative="two-sided", method="auto")
    total = positive + negative
    effect = (positive - negative) / total
    return {"statistic": float(tested.statistic), "p_value": float(tested.pvalue), "matched_rank_biserial": float(effect), "n_nonzero": len(nonzero)}


_REQUIRED_INFERENCE_DESIGN = {
    "inference_requested": True,
    "primary_metric": PRIMARY_METRIC,
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
    "registration_status": "pre_specified_not_registered",
}


def _assess_inference_design(design, *, simulated, incomplete, reviewer_mismatches):
    if design is None:
        return {"status": "design_not_supplied", "eligible": False, "reasons": ["default_descriptive_analysis"]}
    reasons = [key for key, expected in _REQUIRED_INFERENCE_DESIGN.items() if design.get(key) != expected]
    if not isinstance(design.get("sample_size_justification"), str) or not design["sample_size_justification"].strip():
        reasons.append("sample_size_justification")
    if simulated:
        reasons.append("simulated_data")
    if incomplete:
        reasons.append("incomplete_scheme_pairs")
    if reviewer_mismatches:
        reasons.append("different_reviewer_sets")
    return {"status": "eligible" if not reasons else "ineligible", "eligible": not reasons, "reasons": reasons, "design": dict(design)}


def compare_versions(rows, pairs, *, simulated=False, design=None) -> dict:
    pair_ids, used_schemes = set(), set()
    for index, pair in enumerate(pairs, 1):
        required = {"pair_id", "v1_scheme_id", "v2_scheme_id"}
        if not required.issubset(pair):
            raise ValueError(f"pair {index}: missing fields")
        if pair["pair_id"] in pair_ids:
            raise ValueError(f"pair {index}: duplicate pair_id")
        pair_ids.add(pair["pair_id"])
        v1, v2 = pair["v1_scheme_id"], pair["v2_scheme_id"]
        if v1 == v2:
            raise ValueError(f"pair {index}: schemes must differ")
        if v1 in used_schemes or v2 in used_schemes:
            raise ValueError(f"pair {index}: scheme reused across pairs")
        used_schemes.update((v1, v2))
    rows = validate_reviews(rows, {row.get("scheme_id") for row in rows})
    lookup = {(row["reviewer_id"], row["scheme_id"]): row for row in rows}
    incomplete_pair_ids = []
    reviewer_set_mismatch_pair_ids = []
    pair_reviewers = {}
    for pair in pairs:
        v1_reviewers = {r for r, s in lookup if s == pair["v1_scheme_id"]}
        v2_reviewers = {r for r, s in lookup if s == pair["v2_scheme_id"]}
        common = sorted(v1_reviewers & v2_reviewers)
        pair_reviewers[pair["pair_id"]] = common
        if not common:
            incomplete_pair_ids.append(pair["pair_id"])
        elif v1_reviewers != v2_reviewers:
            reviewer_set_mismatch_pair_ids.append(pair["pair_id"])
    inference = _assess_inference_design(
        design,
        simulated=simulated,
        incomplete=incomplete_pair_ids,
        reviewer_mismatches=reviewer_set_mismatch_pair_ids,
    )
    dimensions = {}
    for dimension in DIMENSIONS:
        pair_differences = []
        details = []
        for pair in pairs:
            reviewers = pair_reviewers[pair["pair_id"]]
            differences = [lookup[(r, pair["v2_scheme_id"])][dimension] - lookup[(r, pair["v1_scheme_id"])][dimension] for r in reviewers]
            if differences:
                aggregate = mean(differences)
                pair_differences.append(aggregate)
                details.append({"pair_id": pair["pair_id"], "n_reviewers": len(reviewers), "reviewer_ids": reviewers, "mean_difference": aggregate})
        test = _wilcoxon(pair_differences)
        dimensions[dimension] = {"n_pairs": len(pair_differences), "mean_difference": mean(pair_differences) if pair_differences else None, "pair_results": details, **test}
    ordered = sorted(DIMENSIONS, key=lambda d: dimensions[d]["p_value"])
    previous = 0.0
    m = len(ordered)
    for rank, dimension in enumerate(ordered):
        adjusted = min(1.0, dimensions[dimension]["p_value"] * (m - rank))
        adjusted = max(previous, adjusted)
        previous = adjusted
        dimensions[dimension]["holm_adjusted_p"] = adjusted
        is_primary = dimension == PRIMARY_METRIC
        eligible = inference["eligible"] and is_primary
        dimensions[dimension]["inferentially_eligible"] = eligible
        dimensions[dimension]["inference_status"] = "eligible" if eligible else ("secondary_exploratory" if inference["eligible"] else inference["status"])
        dimensions[dimension]["p_value_role"] = "confirmatory_primary" if eligible else ("exploratory_secondary" if inference["eligible"] else "exploratory_only")
        # The sole prespecified primary outcome is tested at alpha=.05. Holm values
        # remain available for the explicitly exploratory seven-dimension family.
        dimensions[dimension]["significant"] = eligible and dimensions[dimension]["p_value"] < design["alpha"]
    observed_pairs = min((value["n_pairs"] for value in dimensions.values()), default=0)
    primary = dimensions[PRIMARY_METRIC]
    return {
        "simulated": simulated,
        "dimensions": dimensions,
        "primary_metric": PRIMARY_METRIC,
        "secondary_metrics": [dimension for dimension in DIMENSIONS if dimension != PRIMARY_METRIC],
        "n_review_rows": len(rows),
        "n_unique_schemes": len({row["scheme_id"] for row in rows}),
        "n_planned_pairs": len(pairs),
        "n_independent_pairs": observed_pairs,
        "incomplete_pair_ids": incomplete_pair_ids,
        "reviewer_set_mismatch_pair_ids": reviewer_set_mismatch_pair_ids,
        "inference": inference,
        "p_value_role": "confirmatory_primary_only" if inference["eligible"] else "exploratory_only",
        "can_claim_significance": bool(primary["significant"]),
        "can_claim_real_improvement": False,
        "note": "程序只报告统计结果及其适用条件，不自动作方案质量或真实改善宣称。",
    }
