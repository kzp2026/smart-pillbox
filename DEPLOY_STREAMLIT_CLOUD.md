# Streamlit Cloud 部署说明

## 1. 准备 GitHub 仓库

本项目已配置好 Streamlit Cloud 所需文件：
- `app.py` — 主应用
- `app_legacy_current.py` — 旧版单次上传全流程备份入口
- `pages/01_现有流程备份.py` — Streamlit 侧边栏旧版页面
- `requirements.txt` — Python 依赖
- `packages.txt` — 系统包（中文字体）
- `.streamlit/config.toml` — 主题与上传限制
- `scripts/` — 全部阶段脚本
- `data/` — 示例数据（可选）
- `output/` — 预生成结果（可选）

## 2. 在 Streamlit Cloud 新建应用

1. 打开 `https://share.streamlit.io/`
2. 使用 GitHub 账号登录
3. 点击 `Create app` 或 `New app`
4. 选择包含本项目的 GitHub 仓库
5. Branch 选择 `main`
6. Main file path 填写：`app.py`
7. 点击 Deploy

## 3. 使用方式

1. 在“导入评论资产”页输入产品名称、品类，并上传 `.xlsx` / `.xls` / `.csv` 评论数据。
2. 点击“存入知识库”，系统会保存原始评论并抽取基础需求证据。
3. 在“需求生成”页输入新产品和需求描述。
4. 系统会从历史评论知识库中检索证据，生成设计方案、合理性评分和写实渲染提示词。
5. 如需旧版完整流程，请打开侧边栏 `01_现有流程备份`。

## 4. Supabase / PostgreSQL 持久化

推荐在 Streamlit Cloud Secrets 中配置云数据库：
```toml
PRODUCT_KB_DATABASE_URL = "postgresql://user:password@host:5432/postgres"
```

Supabase 项目可在 Project Settings → Database 中复制 PostgreSQL 连接字符串。没有配置时应用会自动回退到本地 SQLite，但 Streamlit Cloud 重启后本地文件不适合长期保存。

## 5. DeepSeek 增强

在 Streamlit Cloud 的“管理应用 → 应用设置 → 秘密”中配置：
```toml
DEEPSEEK_API_KEY = "sk-你的DeepSeek密钥"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
```

配置后，设计方案会由 DeepSeek 润色，第 9 阶段会依据需求、痛点和主题聚类生成更专业的工业设计渲染提示词。

DeepSeek 的托管 API 不提供图片生成端点，因此它不能直接输出写实效果图。写实图片需要另外配置支持图像生成的图片模型；未配置时系统仍会输出 DeepSeek 提示词和离线示意图。

国内写实渲染推荐配置（阿里云百炼 DashScope，支持通义万相 / Qwen-Image）：
```toml
DASHSCOPE_API_KEY = "你的阿里云百炼API Key"
IMAGE_PROVIDER = "dashscope"
IMAGE_MODEL = "qwen-image"
# 也可改用通义万相模型，例如：
# IMAGE_MODEL = "wan2.2-t2i-plus"
```

OpenAI 或其他兼容接口配置：
```toml
IMAGE_API_KEY = "你的图片模型密钥"
IMAGE_MODEL = "gpt-image-1"
IMAGE_QUALITY = "medium"
# 仅兼容接口需要：
# IMAGE_BASE_URL = "https://你的接口地址/v1"
```

配置保存并重启后，进入“设计图片”页点击“生成/重新生成六类写实渲染图”。不要把密钥写入代码或提交到 GitHub。

## 6. 结果持久化

Streamlit Cloud 的运行目录不是长期数据库。新版建议使用 Supabase/PostgreSQL 保存评论知识库；旧版流程仍可在“下载中心”下载完整研究结果归档 ZIP。
