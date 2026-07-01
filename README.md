# 用户评论驱动的产品设计生成系统

本项目用于研究生课题实验：**基于用户评论数据的产品设计研究**。流程从电商评论数据出发，依次完成数据清洗、关键词提取、情感分析、主题聚类、需求-功能-结构映射、Neo4j 知识图谱文件生成、AI 生成参数转化、产品设计方案生成、产品设计图片生成，以及方案评价与优化。

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
| 07 AI生成参数 | 需求、功能、结构转 AI 可识别参数 | `AI生成参数表.xlsx`、`ai_generation_parameters.json` |
| 08 设计方案 | 产品设计文字方案 | `{产品名}产品设计方案.docx` |
| 09 设计图片 | 产品效果图+爆炸图+细节图+三视图+设计展板+产品使用效果图 | `design_images/` |
| 10 方案评价 | 方案评分、优化建议、开题报告摘要 | `方案评价表.xlsx`、`方案优化建议.txt`、`开题报告实验结果摘要.docx` |

核心技术路线为：**用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化**。

新增导出文件包括：
- `需求—功能—结构映射表.xlsx`
- `AI生成参数表.xlsx`
- `ai_generation_parameters.json`
- `prompt_template.txt`
- `方案评价表.xlsx`
- `方案优化建议.txt`
- `优化后AI生成参数.json`
- `开题报告实验结果摘要.docx`

## 4. AI 增强（可选）

设置环境变量启用 DeepSeek 增强文案和工业设计渲染提示词：
```bash
set DEEPSEEK_API_KEY=你的密钥
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-flash
```

配置后：
- 第 8 阶段会自动用 DeepSeek 润色设计方案
- 第 9 阶段会用 DeepSeek 根据需求、痛点和主题聚类优化六类渲染提示词
- DeepSeek 本身不提供图片生成端点；写实产品渲染图仍需另外配置图片生成模型密钥。

国内写实渲染推荐配置（阿里云百炼 DashScope，支持通义万相 / Qwen-Image）：
```toml
DASHSCOPE_API_KEY = "你的阿里云百炼API Key"
IMAGE_PROVIDER = "dashscope"
IMAGE_MODEL = "qwen-image-2.0-pro"
# 如控制台暂未开通参考图模型，可临时改用：
# IMAGE_MODEL = "qwen-image"
# IMAGE_MODEL = "wan2.2-t2i-plus"
```

OpenAI 或其他兼容接口配置：
```toml
IMAGE_API_KEY = "你的图片模型密钥"
IMAGE_MODEL = "gpt-image-1"
IMAGE_QUALITY = "medium"
# 使用 OpenAI Images 兼容接口时再填写：
# IMAGE_BASE_URL = "https://你的接口地址/v1"
```

保存 Streamlit Secrets 并等待应用重启后，在“设计图片”页点击“生成/重新生成六类写实渲染图”。系统会自动补跑缺失的前置阶段，并显示写实图成功数量；失败项目会保留离线示意图。六类写实图会共用一份“产品一致性设计锁”，并优先使用产品效果图作为后续图片的参考图，用于约束爆炸图、细节图、三视图、设计展板和使用效果图保持同一款产品，只改变视角、拆解、特写、展板排版和使用场景。

下载中心支持“一键下载完整研究结果归档.zip”。如果 Streamlit Cloud 重启导致临时结果丢失，可在侧边栏“恢复历史结果归档”中重新导入该 ZIP。

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
