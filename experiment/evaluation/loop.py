from .statistics import DIMENSIONS, validate_reviews


FIELDS = ["change_id", "v1_scheme_id", "v2_scheme_id", "reviewer_id", "low_dimension", "expert_issue", "requirement_id", "function_id", "structure_id", "prompt_field", "old_value", "new_value", "reason"]
PROMPT_FIELDS = {"requirements", "functions", "structure", "layout", "style", "colors", "typography", "controls", "accessibility", "content", "negative_prompt"}


def validate_changes(changes, reviews, requirements, mappings, generation_ids) -> list[dict]:
    reviews = validate_reviews(reviews, {row.get("scheme_id") for row in reviews})
    review_lookup = {(row["reviewer_id"], row["scheme_id"]): row for row in reviews}
    requirement_ids = {row.get("requirement_id") for row in requirements}
    mapping_ids = {(row.get("requirement_id"), row.get("function_id"), row.get("structure_id")) for row in mappings}
    generation_ids = set(generation_ids)
    seen = set()
    result = []
    for index, source in enumerate(changes, 1):
        missing = [field for field in FIELDS if field not in source]
        if missing:
            raise ValueError(f"change {index}: missing fields {missing}")
        row = dict(source)
        if any(not isinstance(row[field], str) or not row[field].strip() for field in FIELDS):
            raise ValueError(f"change {index}: fields must be non-empty strings")
        if row["change_id"] in seen:
            raise ValueError(f"change {index}: duplicate change_id")
        seen.add(row["change_id"])
        if row["low_dimension"] not in DIMENSIONS:
            raise ValueError(f"change {index}: unknown dimension")
        if row["v1_scheme_id"] == row["v2_scheme_id"]:
            raise ValueError(f"change {index}: generations must differ")
        if row["prompt_field"] not in PROMPT_FIELDS:
            raise ValueError(f"change {index}: unknown prompt field")
        review = review_lookup.get((row["reviewer_id"], row["v1_scheme_id"]))
        if review is None or review[row["low_dimension"]] > 3:
            raise ValueError(f"change {index}: no matching low score")
        if row["expert_issue"] != review["issues"]:
            raise ValueError(f"change {index}: expert issue differs from review")
        if row["requirement_id"] not in requirement_ids:
            raise ValueError(f"change {index}: unknown requirement")
        if (row["requirement_id"], row["function_id"], row["structure_id"]) not in mapping_ids:
            raise ValueError(f"change {index}: unknown mapping")
        if row["v1_scheme_id"] not in generation_ids or row["v2_scheme_id"] not in generation_ids:
            raise ValueError(f"change {index}: unknown generation")
        if row["old_value"].strip() == row["new_value"].strip():
            raise ValueError(f"change {index}: value did not change")
        result.append(row)
    return result
