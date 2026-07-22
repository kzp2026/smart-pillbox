from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from v2.adapters.postgres import KnowledgeRepository, clean_text
from v2.domain.models import ImportReport


_KEYWORD_RULES = {
    "提醒反馈": ("提醒", "提示", "声音", "灯", "通知", "忘记", "按时"),
    "安全可靠": ("安全", "稳定", "牢固", "防滑", "可靠", "保护"),
    "操作便利": ("方便", "简单", "容易", "操作", "老人", "父母", "清楚"),
    "容量收纳": ("容量", "收纳", "分格", "分类", "空间", "够用"),
    "外观质感": ("外观", "颜色", "好看", "质感", "材质", "做工"),
    "价格服务": ("价格", "客服", "物流", "安装", "售后", "性价比"),
}


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

        matched = 0
        for title, keywords in _KEYWORD_RULES.items():
            evidence = [comment for comment in cleaned if any(keyword in comment for keyword in keywords)][:3]
            if not evidence:
                continue
            self.repository.add_requirement_once(
                product_id=report.product_id,
                batch_id=report.batch_id,
                title=title,
                description=f"历史评论多次提到{title}相关体验，需要在方案中优先回应。",
                keywords=keywords,
                evidence_text=" | ".join(evidence),
                score=min(100, 55 + len(evidence) * 12),
            )
            matched += 1
        if matched == 0 and cleaned:
            self.repository.add_requirement_once(
                report.product_id,
                report.batch_id,
                "综合体验优化",
                "评论暂未命中明确规则，先作为综合体验证据沉淀。",
                "体验、产品、使用",
                "\n".join(cleaned)[:300],
                60,
            )
        after_requirements = self.repository.count_rows("requirements")
        return KnowledgeImportResult(report, max(0, after_requirements - before_requirements))
