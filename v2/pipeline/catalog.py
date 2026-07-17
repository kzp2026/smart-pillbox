from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageDefinition:
    id: str
    label: str
    script_name: str
    output_pattern: str
    dependency_ids: tuple[str, ...]
    accepts_input: bool = False
    accepts_product_name: bool = False


@dataclass(frozen=True)
class StageGroup:
    id: str
    label: str
    legacy_stage_ids: tuple[str, ...]


LEGACY_STAGES = (
    StageDefinition("01", "评论清洗", "01_clean_comments.py", "cleaned_comments.xlsx", (), True, False),
    StageDefinition("02", "关键词提取", "02_extract_keywords.py", "需求关键词提取结果.xlsx", ("01",), True, False),
    StageDefinition("03", "情感分析", "03_sentiment_analysis.py", "情感分析结果.xlsx", ("01",), True, False),
    StageDefinition("04", "主题聚类", "04_bertopic_clustering.py", "BERTopic主题聚类结果.xlsx", ("01",), True, False),
    StageDefinition("05", "需求映射", "05_build_mapping_database.py", "{product}_需求功能映射数据库.xlsx", ("02", "03", "04"), False, True),
    StageDefinition("06", "Neo4j图谱", "06_build_neo4j_files.py", "neo4j_nodes.csv", ("05",), False, True),
    StageDefinition("07", "AI生成参数", "07_generate_ai_parameters.py", "AI生成参数表.xlsx", ("05", "06"), False, True),
    StageDefinition("08", "设计方案", "07_generate_design_scheme.py", "{product}产品设计方案.docx", ("07",), False, True),
    StageDefinition("09", "设计图片", "08_generate_design_visuals.py", "design_images/{product}产品设计展板.png", ("07", "08"), False, True),
    StageDefinition("10", "方案评价", "09_evaluate_design_scheme.py", "方案评价表.xlsx", ("07", "08"), False, True),
)


V2_STAGES = (
    StageGroup("import", "导入评论资产", ("01",)),
    StageGroup("demand", "需求生成", ()),
    StageGroup("knowledge", "知识库概览", ("02", "03", "04")),
    StageGroup("graph", "需求—功能—结构图谱", ("05", "06")),
    StageGroup("design", "设计方案与评价", ("07", "08", "10")),
    StageGroup("prompt", "工业设计 Prompt", ()),
    StageGroup("images", "AI 图片生成", ("09",)),
)


STAGE_BY_ID = {stage.id: stage for stage in LEGACY_STAGES}
