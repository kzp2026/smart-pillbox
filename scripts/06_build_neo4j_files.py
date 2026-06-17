from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from common import ensure_output_dir, resolve_latest_output_path, stable_id


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def add_node(nodes: dict[str, dict], node_id: str, label: str, name: str, category: str = "", description: str = "", weight: float = 1.0, source: str = "") -> None:
    nodes[node_id] = {
        "node_id": node_id,
        "label": label,
        "name": name,
        "category": category,
        "description": description,
        "source": source,
        "weight": weight,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="第六阶段：生成 Neo4j 可导入节点表、关系表和 Cypher 文件")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--product-name", default="产品", help="产品名称")
    args = parser.parse_args()

    product_name = args.product_name
    output_dir = ensure_output_dir(args.output_dir)
    mapping_path = output_dir / f"{product_name}_需求功能映射数据库.xlsx"
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    keyword_path = output_dir / "需求关键词提取结果.xlsx"

    req_df = read_sheet(mapping_path, "用户需求表")
    func_df = read_sheet(mapping_path, "产品功能表")
    struct_df = read_sheet(mapping_path, "产品结构表")
    req_func_df = read_sheet(mapping_path, "需求功能映射")
    func_struct_df = read_sheet(mapping_path, "功能结构映射")
    topic_req_df = read_sheet(mapping_path, "主题需求映射")
    topic_df = read_sheet(topic_path, "主题汇总")
    keyword_df = read_sheet(keyword_path, "关键词排名")

    nodes: dict[str, dict] = {}
    relationships: list[dict] = []

    product_id = f"PRODUCT_{product_name}"
    add_node(nodes, product_id, "Product", product_name, "研究对象", f"基于用户评论数据的{product_name}产品设计研究对象", 1.0, "论文实验")

    for _, row in req_df.iterrows():
        req_id = str(row.get("req_id", ""))
        if not req_id:
            continue
        add_node(
            nodes, req_id, "Requirement",
            str(row.get("需求名称", "")), str(row.get("需求类别", "")),
            str(row.get("需求描述", "")), float(row.get("重要度", 1) or 1),
            str(row.get("来源关键词", "")),
        )
        relationships.append({
            "source_id": product_id, "target_id": req_id,
            "type": "HAS_REQUIREMENT", "weight": row.get("重要度", 1),
            "reason": "产品对象包含由用户评论抽取出的需求",
        })

    for _, row in func_df.iterrows():
        func_id = str(row.get("func_id", ""))
        if not func_id:
            continue
        add_node(nodes, func_id, "Function", str(row.get("功能名称", "")), str(row.get("功能类别", "")), str(row.get("功能描述", "")), float(row.get("优先级", 1) or 1), "映射数据库")

    for _, row in struct_df.iterrows():
        struct_id = str(row.get("structure_id", ""))
        if not struct_id:
            continue
        add_node(nodes, struct_id, "Structure", str(row.get("结构名称", "")), str(row.get("结构类型", "")), str(row.get("结构描述", "")), 1.0, "映射数据库")

    for _, row in req_func_df.iterrows():
        relationships.append({
            "source_id": row.get("req_id", ""), "target_id": row.get("func_id", ""),
            "type": "SATISFIED_BY", "weight": row.get("映射强度", 1),
            "reason": row.get("映射理由", ""),
        })

    for _, row in func_struct_df.iterrows():
        relationships.append({
            "source_id": row.get("func_id", ""), "target_id": row.get("structure_id", ""),
            "type": "REALIZED_BY", "weight": 1,
            "reason": row.get("映射理由", ""),
        })

    for _, row in topic_df.iterrows():
        topic_id = f"TOPIC_{row.get('topic_id', '')}"
        if topic_id == "TOPIC_":
            continue
        add_node(nodes, topic_id, "Topic", str(row.get("主题名称", topic_id)), "用户评论主题", str(row.get("主题关键词", "")), float(row.get("评论数", 1) or 1), str(row.get("algorithm", "")))

    for _, row in topic_req_df.iterrows():
        relationships.append({
            "source_id": f"TOPIC_{row.get('topic_id', '')}", "target_id": row.get("req_id", ""),
            "type": "BELONGS_TO_TOPIC", "weight": 1,
            "reason": row.get("映射依据", ""),
        })

    for _, row in keyword_df.head(50).iterrows():
        keyword = str(row.get("关键词", ""))
        if not keyword:
            continue
        keyword_id = stable_id("KEY", keyword)
        add_node(nodes, keyword_id, "Keyword", keyword, "", "TF-IDF 抽取的用户需求关键词", float(row.get("TF-IDF权重", 1) or 1), "需求关键词提取结果")
        for _, req in req_df.iterrows():
            if keyword in str(req.get("来源关键词", "")):
                relationships.append({
                    "source_id": keyword_id, "target_id": req.get("req_id", ""),
                    "type": "MENTIONS_KEYWORD", "weight": row.get("TF-IDF权重", 1),
                    "reason": "关键词支撑该用户需求",
                })

    node_ids = set(nodes)
    relationships = [rel for rel in relationships if str(rel.get("source_id", "")) in node_ids and str(rel.get("target_id", "")) in node_ids]

    nodes_path = output_dir / "neo4j_nodes.csv"
    rels_path = output_dir / "neo4j_relationships.csv"
    cypher_path = output_dir / "import_neo4j.cypher"

    with open(nodes_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["node_id", "label", "name", "category", "description", "source", "weight"])
        writer.writeheader()
        writer.writerows(nodes.values())

    with open(rels_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["source_id", "target_id", "type", "weight", "reason"])
        writer.writeheader()
        writer.writerows(relationships)

    relation_types = sorted({rel["type"] for rel in relationships})
    cypher_lines = [
        "// Neo4j 导入脚本：请把 neo4j_nodes.csv 和 neo4j_relationships.csv 放到 Neo4j import 目录",
        "CREATE CONSTRAINT kg_node_id IF NOT EXISTS FOR (n:KGNode) REQUIRE n.node_id IS UNIQUE;",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodes.csv' AS row",
        "MERGE (n:KGNode {node_id: row.node_id})",
        "SET n.label = row.label,",
        "    n.name = row.name,",
        "    n.category = row.category,",
        "    n.description = row.description,",
        "    n.source = row.source,",
        "    n.weight = toFloat(row.weight);",
        "",
    ]

    for relation_type in relation_types:
        cypher_lines.extend([
            f"// 导入 {relation_type} 关系",
            "LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row",
            f"WITH row WHERE row.type = '{relation_type}'",
            "MATCH (source:KGNode {node_id: row.source_id})",
            "MATCH (target:KGNode {node_id: row.target_id})",
            f"MERGE (source)-[r:{relation_type}]->(target)",
            "SET r.weight = toFloat(row.weight),",
            "    r.reason = row.reason;",
            "",
        ])

    cypher_path.write_text("\n".join(cypher_lines), encoding="utf-8")

    print(f"产品名称：{product_name}")
    print(f"节点数：{len(nodes)}")
    print(f"关系数：{len(relationships)}")
    print(f"已生成：{nodes_path}")
    print(f"已生成：{rels_path}")
    print(f"已生成：{cypher_path}")


if __name__ == "__main__":
    main()
