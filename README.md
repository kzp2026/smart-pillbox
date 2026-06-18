# 用户评论驱动的产品设计生成系统

本项目用于研究生课题实验：**基于用户评论数据的产品设计研究**。流程从电商评论数据出发，依次完成数据清洗、关键词提取、情感分析、主题聚类、需求-功能-结构映射、Neo4j 知识图谱文件生成、产品设计方案生成，以及产品效果图、爆炸图、细节图、三视图、设计展板和产品使用效果图生成。

> 🆕 **支持任意产品！** 输入产品名称，上传评论数据，系统自动完成全流程分析。

## 1. 快速开始

### 在线使用（Streamlit Cloud）
直接访问部署好的网址，输入产品名称 → 上传评论数据 → 一键生成。

### 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 2. 数据输入

在侧边栏输入产品名称，上传评论数据（.xlsx / .xls / .csv），系统自动识别评论列。

## 3. 分阶段说明

| 阶段 | 说明 | 输出 |
|------|------|------|
| 01 评论清洗 | 读取+清洗评论，分词 | `cleaned_comments.xlsx` |
| 02 关键词提取 | TF-IDF 用户需求关键词 | `需求关键词提取结果.xlsx` |
| 03 情感分析 | 中文评论情感与痛点识别 | `情感分析结果.xlsx` |
| 04 主题聚类 | BERTopic/KMeans 主题聚类 | `BERTopic主题聚类结果.xlsx` |
| 05 需求映射 | 需求→功能→结构自动映射 | `{产品名}_需求功能映射数据库.xlsx` |
| 06 Neo4j图谱 | 知识图谱节点、关系、Cypher | `neo4j_nodes.csv` 等 |
| 07 设计方案 | 产品设计文字方案 | `{产品名}产品设计方案.docx` |
| 08 设计图片 | 产品效果图+爆炸图+细节图+三视图+设计展板+产品使用效果图 | `design_images/` |

## 4. AI 增强（可选）

设置环境变量启用 DeepSeek 增强文案和工业设计渲染提示词：
```bash
set DEEPSEEK_API_KEY=你的密钥
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-flash
```

配置后：
- 第 7 阶段会自动用 DeepSeek 润色设计方案
- 第 8 阶段会用 DeepSeek 根据需求、痛点和主题聚类优化六类渲染提示词
- DeepSeek 本身不提供图片生成端点；写实产品渲染图仍需另外配置 `IMAGE_API_KEY`

Streamlit Cloud 请在“管理应用 → 应用设置 → 秘密”中使用根级配置：
```toml
DEEPSEEK_API_KEY = "sk-你的DeepSeek密钥"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
```

不配置时系统使用离线模板和示意图，流程仍可完整运行。

## 5. 环境安装
```bash
pip install -r requirements.txt
pip install bertopic      # 可选，失败时自动切换 KMeans
```

`openai` 已包含在 `requirements.txt` 中，用于 DeepSeek 和其他 OpenAI 兼容接口。
