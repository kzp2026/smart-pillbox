# Streamlit Cloud 部署说明

## 1. 准备 GitHub 仓库

Streamlit Cloud 需要从 GitHub 仓库部署。请把本项目根目录中的以下内容提交到 GitHub：

- `app.py`
- `requirements.txt`
- `packages.txt`
- `.streamlit/config.toml`
- `scripts/`
- `data/`（可选：如需默认演示数据）
- `output/`（可选：如需默认展示已生成结果和高保真图片）
- `README.md`

不需要提交：

- `__pycache__/`
- 临时日志文件

## 2. 在 Streamlit Cloud 新建应用

1. 打开 `https://share.streamlit.io/`。
2. 使用 GitHub 账号登录。
3. 点击 `Create app` 或 `New app`。
4. 选择包含本项目的 GitHub 仓库。
5. Branch 选择 `main` 或你的实际分支。
6. Main file path 填写：

```text
app.py
```

7. 点击部署。

## 3. 部署后使用方式

打开 Streamlit Cloud 分配的网址后：

1. 上传 `.xlsx`、`.xls` 或 `.csv` 评论数据。
2. 点击“一键生成全部研究结果”。
3. 在网页标签页中查看评论清洗、需求关键词、痛点、主题聚类、映射数据库、知识图谱、设计方案、设计图片和展板。
4. 在“下载中心”下载所有实验结果文件。

## 4. 可选大模型增强

如果需要在云端启用第 7 阶段的大模型文案增强，请在 Streamlit Cloud 的 `Secrets` 中配置：

```toml
LLM_API_KEY = "你的密钥"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"
```

不配置时，系统会使用离线模板生成设计方案，流程仍然可以完整运行。
