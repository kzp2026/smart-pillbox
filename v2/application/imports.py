from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

from v2.adapters.postgres import KnowledgeRepository, clean_text
from v2.domain.models import ImportReport
from experiment.pipeline.semantics import CATALOG, derive_requirements


_KEYWORD_RULES = {name: terms for _key, name, terms, _function, _structure in CATALOG}


@dataclass(frozen=True)
class KnowledgeImportResult:
    report: ImportReport
    new_requirement_count: int


class ImportService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def import_comments(
        self,
        product_name: str,
        category: str,
        source_filename: str,
        comments: Sequence[str],
        metadata: Sequence[Mapping[str, object]] | None = None,
    ) -> KnowledgeImportResult:
        metadata_rows = list(metadata or ())
        cleaned_pairs = [
            (clean_text(comment), metadata_rows[index] if index < len(metadata_rows) else {})
            for index, comment in enumerate(comments)
            if clean_text(comment)
        ]
        cleaned = [comment for comment, _ in cleaned_pairs]
        cleaned_metadata = [row for _, row in cleaned_pairs]
        before_requirements = self.repository.count_rows("requirements")
        report = self.repository.ingest_comments(
            product_name, category, source_filename, cleaned, metadata=cleaned_metadata
        )
        if report.inserted_count == 0:
            return KnowledgeImportResult(report, 0)

        records = [{"comment_id": f"v2-import-{index}", "cleaned_comment": comment}
                   for index, comment in enumerate(cleaned)]
        candidates = derive_requirements(records)
        matched = 0
        for candidate in candidates:
            if candidate["review_status"] == "needs_naming":
                continue
            title = candidate["requirement_name"]
            evidence = [item["text"] for item in candidate["source_evidence_spans"][:3]]
            trace = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
            self.repository.add_requirement_once(
                product_id=report.product_id,
                batch_id=report.batch_id,
                title=title,
                description=f"{candidate['requirement_description']}\n候选追溯：{trace}",
                keywords=candidate["keywords"],
                evidence_text=trace,
                score=min(100, round(candidate["importance_score"] * 100)),
            )
            matched += 1
        after_requirements = self.repository.count_rows("requirements")
        return KnowledgeImportResult(report, max(0, after_requirements - before_requirements))
