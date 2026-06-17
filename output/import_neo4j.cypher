// Neo4j 导入脚本：请把 neo4j_nodes.csv 和 neo4j_relationships.csv 放到 Neo4j import 目录
CREATE CONSTRAINT kg_node_id IF NOT EXISTS FOR (n:KGNode) REQUIRE n.node_id IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodes.csv' AS row
MERGE (n:KGNode {node_id: row.node_id})
SET n.label = row.label,
    n.name = row.name,
    n.category = row.category,
    n.description = row.description,
    n.source = row.source,
    n.weight = toFloat(row.weight);

// 导入 BELONGS_TO_TOPIC 关系
LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row
WITH row WHERE row.type = 'BELONGS_TO_TOPIC'
MATCH (source:KGNode {node_id: row.source_id})
MATCH (target:KGNode {node_id: row.target_id})
MERGE (source)-[r:BELONGS_TO_TOPIC]->(target)
SET r.weight = toFloat(row.weight),
    r.reason = row.reason;

// 导入 HAS_REQUIREMENT 关系
LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row
WITH row WHERE row.type = 'HAS_REQUIREMENT'
MATCH (source:KGNode {node_id: row.source_id})
MATCH (target:KGNode {node_id: row.target_id})
MERGE (source)-[r:HAS_REQUIREMENT]->(target)
SET r.weight = toFloat(row.weight),
    r.reason = row.reason;

// 导入 MENTIONS_KEYWORD 关系
LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row
WITH row WHERE row.type = 'MENTIONS_KEYWORD'
MATCH (source:KGNode {node_id: row.source_id})
MATCH (target:KGNode {node_id: row.target_id})
MERGE (source)-[r:MENTIONS_KEYWORD]->(target)
SET r.weight = toFloat(row.weight),
    r.reason = row.reason;

// 导入 REALIZED_BY 关系
LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row
WITH row WHERE row.type = 'REALIZED_BY'
MATCH (source:KGNode {node_id: row.source_id})
MATCH (target:KGNode {node_id: row.target_id})
MERGE (source)-[r:REALIZED_BY]->(target)
SET r.weight = toFloat(row.weight),
    r.reason = row.reason;

// 导入 SATISFIED_BY 关系
LOAD CSV WITH HEADERS FROM 'file:///neo4j_relationships.csv' AS row
WITH row WHERE row.type = 'SATISFIED_BY'
MATCH (source:KGNode {node_id: row.source_id})
MATCH (target:KGNode {node_id: row.target_id})
MERGE (source)-[r:SATISFIED_BY]->(target)
SET r.weight = toFloat(row.weight),
    r.reason = row.reason;
