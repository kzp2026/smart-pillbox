# Streamlit Cloud 部署说明

## 1. 准备 GitHub 仓库

本项目已配置好 Streamlit Cloud 所需文件：
- `app.py` — 主应用
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

1. 在侧边栏输入产品名称（如：蓝牙耳机、咖啡机、智能手表...）
2. 上传 `.xlsx` / `.xls` / `.csv` 评论数据
3. 点击"一键生成全部研究结果"
4. 在各标签页查看：评论清洗、关键词、痛点、主题聚类、映射数据库、知识图谱、设计方案、设计图
5. 在"下载中心"下载所有实验结果文件

## 4. 可选大模型增强

在 Streamlit Cloud 的 `Secrets` 中配置：
```toml
LLM_API_KEY = "你的密钥"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"
```
配置后设计方案会由 LLM 润色，效果图会尝试 AI 真实渲染。
