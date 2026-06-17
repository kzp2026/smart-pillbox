# 智能药盒用户评论分析与产品设计生成流程

本项目用于研究生课题实验：**基于用户评论数据的智能药盒产品设计研究**。流程从电商评论数据出发，依次完成数据清洗、关键词提取、情感分析、主题聚类、需求功能结构映射、Neo4j 知识图谱文件生成、产品设计方案生成，以及设计效果图、三视图、爆炸图、场景使用效果图和产品设计展板生成。

## 1. 数据输入

默认数据路径为：

```bash
data/京东智能药盒评论
```

脚本会按顺序自动尝试：

```bash
data/京东智能药盒评论.xlsx
data/京东智能药盒评论.xls
data/京东智能药盒评论.csv
```

如果 Excel 列名不是“评论内容”，脚本会自动识别最可能的评论文本列。当前样例数据识别到的评论列是 `评论`。

## 2. 环境安装

建议先安装稳定核心依赖：

```bash
pip install -r requirements.txt
```

`BERTopic` 是可选增强项，安装失败不会影响基础流程，因为第 4 阶段会自动切换为 `KMeans + TF-IDF`：

```bash
pip install bertopic
```

如需第 7 阶段使用 OpenAI/DeepSeek 兼容大模型增强文案，可额外安装：

```bash
pip install openai
```

并设置环境变量：

```bash
set LLM_API_KEY=你的密钥
set LLM_BASE_URL=https://api.deepseek.com
set LLM_MODEL=deepseek-chat
```

不设置这些变量时，系统会使用离线模板生成设计方案。

## 3. 分阶段运行

每个阶段都可以单独运行，输出统一保存在 `output` 文件夹。

### 01 评论数据读取与清洗

```bash
python scripts/01_clean_comments.py --input data/京东智能药盒评论 --output-dir output
```

输出文件：

- `output/cleaned_comments.xlsx`

论文作用：形成规范化实验语料，包含原始评论、清洗评论、分词结果、评论长度和词数，是后续所有分析的基础数据。

### 02 TF-IDF 用户需求关键词提取

```bash
python scripts/02_extract_keywords.py --output-dir output
```

输出文件：

- `output/需求关键词提取结果.xlsx`

论文作用：从用户评论中提取高权重需求关键词，用于说明用户关注点、需求强度和关键词共现关系。

### 03 中文评论情感分析

```bash
python scripts/03_sentiment_analysis.py --output-dir output
```

输出文件：

- `output/情感分析结果.xlsx`

论文作用：识别用户满意点和痛点，为产品改进优先级和设计机会点提供情感证据。

### 04 BERTopic 或 KMeans 主题聚类

```bash
python scripts/04_bertopic_clustering.py --output-dir output
```

输出文件：

- `output/BERTopic主题聚类结果.xlsx`

论文作用：把评论聚合为若干需求主题，支持从“单条评论”上升到“群体需求主题”的分析。

如果 BERTopic 未安装或运行失败，脚本会自动使用 `KMeans + TF-IDF` 或纯 Python KMeans 兜底，输出文件名保持一致。

### 05 构建需求-功能-结构映射数据库

```bash
python scripts/05_build_mapping_database.py --output-dir output
```

输出文件：

- `output/智能药盒需求功能映射数据库.xlsx`

论文作用：把评论分析结果转化为“用户需求-产品功能-产品结构”链条，是产品设计推导和知识图谱构建的核心中间数据。

### 06 生成 Neo4j 可导入文件

```bash
python scripts/06_build_neo4j_files.py --output-dir output
```

输出文件：

- `output/neo4j_nodes.csv`
- `output/neo4j_relationships.csv`
- `output/import_neo4j.cypher`

论文作用：用于构建需求知识图谱，展示需求、功能、结构、主题和关键词之间的关联。

Neo4j 使用方法：

1. 将 `neo4j_nodes.csv`、`neo4j_relationships.csv`、`import_neo4j.cypher` 复制到 Neo4j 的 `import` 目录。
2. 在 Neo4j Browser 中运行 `import_neo4j.cypher`。

### 07 生成智能药盒产品设计方案

```bash
python scripts/07_generate_design_scheme.py --output-dir output
```

输出文件：

- `output/智能药盒产品设计方案.txt`
- `output/智能药盒产品设计方案.docx`

论文作用：作为实验最终设计输出，说明如何从用户评论数据推导产品定位、功能方案、结构方案和交互流程。

### 08 生成设计图片与展板

```bash
python scripts/08_generate_design_visuals.py --output-dir output
```

输出文件：

- `output/design_images/智能药盒设计效果图.png`
- `output/design_images/智能药盒三视图.png`
- `output/design_images/智能药盒爆炸图.png`
- `output/design_images/智能药盒场景使用效果图.png`
- `output/design_images/智能药盒产品设计展板.png`
- `output/design_images/设计图像生成提示词.txt`
- `output/design_images/设计图像清单.xlsx`

论文作用：用于展示最终产品概念、结构关系、使用场景和答辩展板。代码会先生成稳定可复现的示意图，同时保留可复制到图像生成模型的提示词，便于后续制作更高保真渲染图。

## 4. 一键运行完整流程

```bash
python scripts/01_clean_comments.py --input data/京东智能药盒评论 --output-dir output
python scripts/02_extract_keywords.py --output-dir output
python scripts/03_sentiment_analysis.py --output-dir output
python scripts/04_bertopic_clustering.py --output-dir output
python scripts/05_build_mapping_database.py --output-dir output
python scripts/06_build_neo4j_files.py --output-dir output
python scripts/07_generate_design_scheme.py --output-dir output
python scripts/08_generate_design_visuals.py --output-dir output
```

完整流程生成的主要结果文件包括：

- `cleaned_comments.xlsx`
- `需求关键词提取结果.xlsx`
- `情感分析结果.xlsx`
- `BERTopic主题聚类结果.xlsx`
- `智能药盒需求功能映射数据库.xlsx`
- `neo4j_nodes.csv`
- `neo4j_relationships.csv`
- `import_neo4j.cypher`
- `智能药盒产品设计方案.docx`
- `智能药盒产品设计方案.txt`
- `design_images/智能药盒设计效果图.png`
- `design_images/智能药盒三视图.png`
- `design_images/智能药盒爆炸图.png`
- `design_images/智能药盒场景使用效果图.png`
- `design_images/智能药盒产品设计展板.png`

## 5. Streamlit 网页系统

启动方式：

```bash
streamlit run app.py
```

网页系统支持：

- 上传 `.xlsx`、`.xls`、`.csv` 评论数据。
- 运行单个阶段或一键运行完整流程。
- 在线查看每一步实验结果，包括清洗数据、产品需求关键词、痛点、满意点、主题聚类、需求-功能-结构映射、知识图谱节点关系、设计方案、设计图片与展板。
- 下载全部实验结果文件。

## 6. 论文实验文件用途汇总

| 文件 | 实验作用 |
|---|---|
| `cleaned_comments.xlsx` | 规范化评论语料，支撑后续文本挖掘 |
| `需求关键词提取结果.xlsx` | 展示 TF-IDF 关键词、共现关系和评论证据 |
| `情感分析结果.xlsx` | 识别满意点和痛点，支撑需求优先级判断 |
| `BERTopic主题聚类结果.xlsx` | 聚合评论主题，形成用户需求主题层 |
| `智能药盒需求功能映射数据库.xlsx` | 建立用户需求到产品功能、产品结构的映射 |
| `neo4j_nodes.csv` | Neo4j 知识图谱节点数据 |
| `neo4j_relationships.csv` | Neo4j 知识图谱关系数据 |
| `import_neo4j.cypher` | Neo4j 图谱导入脚本 |
| `智能药盒产品设计方案.docx` | 最终产品设计方案，可作为论文实验输出 |
| `智能药盒产品设计方案.txt` | 纯文本版设计方案，便于复制和二次编辑 |
| `design_images/智能药盒设计效果图.png` | 展示智能药盒整体造型和核心功能 |
| `design_images/智能药盒三视图.png` | 展示正视、俯视、侧视结构关系 |
| `design_images/智能药盒爆炸图.png` | 展示产品模块层级和结构组成 |
| `design_images/智能药盒场景使用效果图.png` | 展示家庭老人用药与远程监护场景 |
| `design_images/智能药盒产品设计展板.png` | 用于课程汇报、论文答辩和成果展示 |

## 7. 稳定性说明

- 未安装 `jieba` 时，清洗脚本会使用内置领域词典和简单 n-gram 分词兜底。
- 未安装 `SnowNLP` 时，情感分析会使用词典规则和评分字段兜底。
- 未安装 `BERTopic` 或 `scikit-learn` 时，主题聚类会使用纯 Python KMeans 兜底。
- 未配置大模型 API 时，设计方案会使用离线模板生成，保证实验可复现。
