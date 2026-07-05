from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import date, datetime, time
from decimal import Decimal
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.common import build_cleaned_dataframe
from scripts.product_knowledge_base import (
    DEFAULT_DB_PATH,
    ProductKnowledgeBase,
    generate_design_package,
    normalize_database_url,
)
from scripts.upload_parsing import candidate_comment_columns, default_comment_column, extract_comments, read_upload_table


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output" / "knowledge_runs"
LEGACY_OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_IMAGE_MODEL = "qwen-image-2.0-pro-2026-06-22"
APP_VERSION = "2026-07-05-six-prompts-v2"
IMAGE_MODEL_OPTIONS = [
    DEFAULT_IMAGE_MODEL,
    "qwen-image-2.0-pro",
    "qwen-image-max",
    "qwen-image-plus",
    "wan2.2-t2i-plus",
]


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = os.getenv(name, default)
    return str(value or "").strip()


def get_database_url() -> str:
    return get_secret("PRODUCT_KB_DATABASE_URL") or get_secret("DATABASE_URL") or normalize_database_url()


def safe_generation_payload(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): safe_generation_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [safe_generation_payload(item) for item in value]
    return str(value)


def as_plain_json(value: object) -> object:
    return json.loads(json.dumps(safe_generation_payload(value), ensure_ascii=False, default=str))


@st.cache_resource(show_spinner=False)
def get_kb(database_url: str, owner_id: str) -> ProductKnowledgeBase:
    kb = ProductKnowledgeBase(database_url=database_url, owner_id=owner_id)
    kb.initialize()
    return kb


@st.cache_data(show_spinner=False, max_entries=8)
def parse_uploaded_table(filename: str, file_bytes: bytes) -> pd.DataFrame:
    return read_upload_table(filename, file_bytes)


def load_uploaded_table(uploaded_file) -> pd.DataFrame:
    return parse_uploaded_table(uploaded_file.name, uploaded_file.getvalue())


def derive_requirements_from_comments(product_id: int, batch_id: int, comments: list[str], kb: ProductKnowledgeBase) -> int:
    keyword_rules = {
        "提醒反馈": ["提醒", "提示", "声音", "灯", "通知", "忘记", "按时"],
        "安全可靠": ["安全", "稳定", "牢固", "防滑", "可靠", "保护"],
        "操作便利": ["方便", "简单", "容易", "操作", "老人", "父母", "清楚"],
        "容量收纳": ["容量", "收纳", "分格", "分类", "空间", "够用"],
        "外观质感": ["外观", "颜色", "好看", "质感", "材质", "做工"],
        "价格服务": ["价格", "客服", "物流", "安装", "售后", "性价比"],
    }
    added = 0
    joined = "\n".join(comments)
    for title, keywords in keyword_rules.items():
        evidence = [comment for comment in comments if any(keyword in comment for keyword in keywords)][:3]
        if not evidence:
            continue
        score = min(100, 55 + len(evidence) * 12)
        kb.add_requirement(
            product_id=product_id,
            batch_id=batch_id,
            title=title,
            description=f"历史评论多次提到{title}相关体验，需要在方案中优先回应。",
            keywords=keywords,
            evidence_text=" | ".join(evidence),
            score=score,
        )
        added += 1
    if added == 0 and comments:
        kb.add_requirement(
            product_id=product_id,
            batch_id=batch_id,
            title="综合体验优化",
            description="评论暂未命中明确规则，先作为综合体验证据沉淀。",
            keywords="体验、产品、使用",
            evidence_text=joined[:300],
            score=60,
        )
        added = 1
    return added


def load_design_visuals_module():
    module_path = ROOT_DIR / "scripts" / "08_generate_design_visuals.py"
    spec = importlib.util.spec_from_file_location("design_visuals_for_kb_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.path.insert(0, str(ROOT_DIR / "scripts"))
    spec.loader.exec_module(module)
    return module


def build_dashscope_config(api_key: str, model: str) -> dict:
    module = load_design_visuals_module()
    return {
        "provider": "dashscope",
        "api_key": api_key,
        "base_url": os.getenv("DASHSCOPE_IMAGE_API_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"),
        "multimodal_url": os.getenv("DASHSCOPE_MULTIMODAL_API_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"),
        "task_url": os.getenv("DASHSCOPE_TASK_API_URL", "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"),
        "model": DEFAULT_IMAGE_MODEL if model == "qwen-image" else model,
        "quality": "standard",
        "custom_base_url": bool(os.getenv("DASHSCOPE_IMAGE_API_URL")),
        "force_reference_model": model == "qwen-image",
        "prompt_extend": False,
        "negative_prompt": module.get_image_api_config().get("negative_prompt", ""),
        "seed": "",
    }


def generate_dashscope_render(prompt: str, target_product: str, api_key: str, model: str, image_index: int = 1) -> Path | None:
    if not api_key:
        return None
    module = load_design_visuals_module()
    safe_name = "".join(char if char.isalnum() or "\u4e00" <= char <= "\u9fff" else "_" for char in target_product)[:40] or "product"
    image_dir = OUTPUT_DIR / "dashscope_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    output_path = image_dir / f"{safe_name}_效果图_{image_index:02d}.png"
    ok = module.generate_ai_image(
        prompt,
        output_path,
        size="1024x1024",
        reference_path=None,
        config=build_dashscope_config(api_key, model),
    )
    return output_path if ok and output_path.exists() else None


def get_image_prompts(package: dict | None) -> list[str]:
    if not package:
        return []
    prompts = package.get("image_prompts") or []
    if not prompts and package.get("image_prompt_text"):
        prompts = [package["image_prompt_text"]]
    return [str(prompt).strip() for prompt in prompts if str(prompt).strip()][:6]


def get_latest_image_paths() -> list[Path]:
    values = st.session_state.get("latest_image_paths", [])
    if isinstance(values, str):
        values = [values]
    legacy_value = st.session_state.get("latest_image_path", "")
    if legacy_value and legacy_value not in values:
        values = [legacy_value, *values]
    paths = []
    for value in values:
        path = Path(str(value))
        if path.exists():
            paths.append(path)
    return paths[:6]


def store_latest_image_paths(paths: list[Path]) -> None:
    existing = [str(path) for path in get_latest_image_paths()]
    merged = existing + [str(path) for path in paths if str(path) not in existing]
    st.session_state["latest_image_paths"] = merged[:6]
    if merged:
        st.session_state["latest_image_path"] = merged[0]


def render_image_download_grid(image_paths: list[Path], key_prefix: str) -> None:
    if not image_paths:
        st.info("还没有效果图。可以用阿里云百炼生成 6 张效果图，或复制 prompt 到其他生图工具。")
        return
    columns = st.columns(3)
    for index, image_path in enumerate(image_paths[:6], start=1):
        with columns[(index - 1) % 3]:
            st.image(str(image_path), caption=f"效果图 {index}", use_container_width=True)
            st.download_button(
                f"下载本次效果图 {index}",
                data=image_path.read_bytes(),
                file_name=image_path.name,
                mime="image/png",
                use_container_width=True,
                key=f"{key_prefix}_image_download_{index}",
            )


def render_prompt_gallery(package: dict, dashscope_api_key: str, image_model: str, button_key: str) -> None:
    prompts = get_image_prompts(package)
    st.subheader("prompt")
    if prompts:
        for index, prompt in enumerate(prompts, start=1):
            st.markdown(f"**prompt {index}**")
            st.code(prompt, language="text")
    else:
        st.info("当前方案还没有 prompt。")

    st.subheader("效果图预览")
    render_image_download_grid(get_latest_image_paths(), button_key)

    if st.button(f"用阿里云百炼生成 {len(prompts) or 6} 张效果图", use_container_width=True, disabled=not dashscope_api_key or not prompts, key=button_key):
        generated_paths: list[Path] = []
        progress = st.progress(0)
        status = st.empty()
        for index, prompt in enumerate(prompts, start=1):
            status.write(f"正在生成第 {index}/{len(prompts)} 张效果图...")
            generated_image_path = generate_dashscope_render(
                prompt,
                package.get("target_product", "product"),
                dashscope_api_key,
                image_model,
                index,
            )
            if generated_image_path:
                generated_paths.append(generated_image_path)
            progress.progress(int(index / len(prompts) * 100))
        if generated_paths:
            store_latest_image_paths(generated_paths)
            st.success(f"已生成 {len(generated_paths)} 张效果图。")
            render_image_download_grid(get_latest_image_paths(), f"{button_key}_generated")
        else:
            st.error("效果图生成失败，请检查百炼模型权限、余额、Key 或网络。prompt 已保留，可复制到图像模型手动生成。")
    elif not dashscope_api_key:
        st.caption("填写阿里云百炼 Key 后可在这里直接生成 6 张效果图。")


def render_quality_report(package: dict) -> None:
    score = int(package["quality_score"])
    status = package["quality_status"]
    st.metric("合理性评分", f"{score}/100", status)
    report = package["quality_report"]
    checks_df = pd.DataFrame({"检查项": report["checks"]})
    st.dataframe(checks_df, use_container_width=True, hide_index=True)
    if report["warnings"]:
        for warning in report["warnings"]:
            st.warning(warning)
    else:
        st.success("证据链、需求转译、输出完整性达到当前质量门槛。")


def load_legacy_sheet(filename: str, sheet_name: str | None = None) -> pd.DataFrame:
    path = LEGACY_OUTPUT_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return load_legacy_sheet_cached(str(path), sheet_name or "", path.stat().st_mtime_ns)


@st.cache_data(show_spinner=False, max_entries=48)
def load_legacy_sheet_cached(path_text: str, sheet_name: str, mtime_ns: int) -> pd.DataFrame:
    path = Path(path_text)
    try:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    except Exception:
        return pd.DataFrame()


def load_legacy_csv(filename: str) -> pd.DataFrame:
    path = LEGACY_OUTPUT_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return load_legacy_csv_cached(str(path), path.stat().st_mtime_ns)


@st.cache_data(show_spinner=False, max_entries=24)
def load_legacy_csv_cached(path_text: str, mtime_ns: int) -> pd.DataFrame:
    path = Path(path_text)
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def show_table(df: pd.DataFrame, title: str, max_rows: int = 80) -> None:
    st.subheader(title)
    if df.empty:
        st.info("该结果尚未生成。可在左侧页面导航打开“01_现有流程备份”运行完整流程。")
        return
    st.dataframe(df.head(max_rows), use_container_width=True)


def show_legacy_file_download(relative_path: str) -> None:
    path = LEGACY_OUTPUT_DIR / relative_path
    if path.exists() and path.is_file():
        st.download_button(
            f"下载 {Path(relative_path).name}",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/octet-stream",
            use_container_width=True,
        )


def format_number(value: int | float | None) -> str:
    return f"{int(value or 0):,}"


def inject_cloud_studio_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --studio-bg: #f6f9ff;
                --studio-panel: rgba(255, 255, 255, 0.92);
                --studio-panel-strong: #ffffff;
                --studio-border: #d9e4f5;
                --studio-border-strong: #b9cef0;
                --studio-text: #0f1f3d;
                --studio-muted: #5f7190;
                --studio-blue: #1677ff;
                --studio-cyan: #18b7cf;
                --studio-green: #22b573;
                --studio-warn: #ff9f1c;
                --studio-shadow: 0 18px 50px rgba(42, 74, 121, 0.11);
            }

            .stApp {
                background:
                    linear-gradient(180deg, rgba(230, 240, 255, 0.78) 0%, rgba(247, 250, 255, 0.96) 38%, #ffffff 100%);
                color: var(--studio-text);
            }

            .block-container {
                max-width: 1480px;
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #f4f8ff 0%, #ffffff 48%, #eef6ff 100%);
                border-right: 1px solid var(--studio-border);
            }

            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
                color: var(--studio-text);
                letter-spacing: 0;
            }

            [data-testid="stSidebar"] [data-testid="stAlert"] {
                border-radius: 8px;
                border: 1px solid rgba(34, 181, 115, 0.24);
                box-shadow: 0 10px 24px rgba(34, 181, 115, 0.08);
            }

            div[data-testid="stTextInput"] input,
            div[data-testid="stTextArea"] textarea,
            div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                border-radius: 8px;
                border-color: var(--studio-border);
                background-color: rgba(255, 255, 255, 0.94);
                color: var(--studio-text);
                -webkit-text-fill-color: var(--studio-text);
            }

            div[data-testid="stTextInput"] input::placeholder,
            div[data-testid="stTextArea"] textarea::placeholder {
                color: #8ba0c0;
                -webkit-text-fill-color: #8ba0c0;
                opacity: 1;
            }

            div[data-testid="stTextInput"] input:focus,
            div[data-testid="stTextArea"] textarea:focus {
                border-color: var(--studio-blue);
                box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.12);
            }

            .stButton > button,
            .stDownloadButton > button {
                border-radius: 8px;
                border: 1px solid var(--studio-border-strong);
                box-shadow: 0 8px 22px rgba(22, 119, 255, 0.10);
                font-weight: 650;
            }

            .stButton > button[kind="primary"] {
                background: linear-gradient(135deg, var(--studio-blue), #0aa6e8);
                border-color: transparent;
            }

            [data-testid="stFileUploader"] section {
                border-radius: 10px;
                border: 1.5px dashed #a9c4ea;
                background: rgba(247, 251, 255, 0.92);
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 0.25rem;
                border-bottom: 1px solid var(--studio-border);
                background: rgba(255, 255, 255, 0.7);
                padding: 0.35rem 0.3rem 0;
                border-radius: 8px 8px 0 0;
            }

            .stTabs [data-baseweb="tab"] {
                height: 44px;
                border-radius: 8px 8px 0 0;
                color: var(--studio-muted);
                font-weight: 650;
                white-space: nowrap;
            }

            .stTabs [aria-selected="true"] {
                color: var(--studio-blue);
                background: #ffffff;
                border: 1px solid var(--studio-border);
                border-bottom-color: #ffffff;
            }

            [data-testid="stMetric"],
            [data-testid="stDataFrame"],
            [data-testid="stExpander"],
            div[data-testid="stAlert"] {
                border-radius: 8px;
            }

            .cloud-studio-shell {
                border: 1px solid var(--studio-border);
                border-radius: 10px;
                background: var(--studio-panel);
                box-shadow: var(--studio-shadow);
                padding: 1.2rem 1.25rem;
                margin-bottom: 1.1rem;
            }

            .studio-topbar {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: 1rem;
            }

            .studio-brand {
                display: flex;
                align-items: flex-start;
                gap: 0.8rem;
            }

            .studio-logo {
                width: 38px;
                height: 38px;
                border-radius: 9px;
                display: grid;
                place-items: center;
                background: linear-gradient(145deg, #1677ff, #18b7cf);
                color: #fff;
                font-weight: 900;
                box-shadow: 0 10px 24px rgba(22, 119, 255, 0.22);
            }

            .studio-title {
                font-size: 2rem !important;
                line-height: 1.16 !important;
                margin: 0;
                color: var(--studio-text);
                letter-spacing: 0;
            }

            .studio-subtitle {
                margin-top: 0.35rem;
                color: var(--studio-muted);
                font-size: 0.95rem;
            }

            .studio-actions {
                display: flex;
                gap: 0.6rem;
                flex-wrap: wrap;
                justify-content: flex-end;
            }

            .studio-pill {
                border-radius: 999px;
                padding: 0.45rem 0.7rem;
                border: 1px solid var(--studio-border);
                background: #ffffff;
                color: var(--studio-muted);
                font-size: 0.82rem;
                font-weight: 700;
            }

            .studio-pill.is-live {
                color: #0a7a4b;
                border-color: rgba(34, 181, 115, 0.28);
                background: rgba(34, 181, 115, 0.08);
            }

            .studio-flow {
                display: flex;
                gap: 0.55rem;
                flex-wrap: wrap;
                margin: 0.75rem 0 1.1rem;
            }

            .studio-step {
                min-height: 42px;
                display: flex;
                align-items: center;
                gap: 0.48rem;
                padding: 0.55rem 0.72rem;
                border: 1px solid var(--studio-border);
                border-radius: 8px;
                background: #ffffff;
                color: var(--studio-muted);
                font-size: 0.86rem;
                font-weight: 700;
            }

            .studio-step span {
                width: 22px;
                height: 22px;
                display: grid;
                place-items: center;
                border-radius: 7px;
                color: #ffffff;
                background: linear-gradient(135deg, var(--studio-blue), var(--studio-cyan));
                font-size: 0.78rem;
            }

            .studio-dashboard {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(320px, 0.8fr);
                gap: 1rem;
            }

            .studio-card {
                border: 1px solid var(--studio-border);
                background: var(--studio-panel-strong);
                border-radius: 8px;
                padding: 1rem;
                min-width: 0;
            }

            .studio-card-title {
                margin: 0 0 0.75rem;
                color: var(--studio-text);
                font-size: 1rem;
                font-weight: 800;
            }

            .studio-metrics {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                border: 1px solid var(--studio-border);
                border-radius: 8px;
                overflow: hidden;
            }

            .studio-metric {
                padding: 0.86rem 0.8rem;
                border-right: 1px solid var(--studio-border);
                min-width: 0;
            }

            .studio-metric:last-child {
                border-right: 0;
            }

            .studio-metric small {
                display: block;
                color: var(--studio-muted);
                font-size: 0.76rem;
                margin-bottom: 0.28rem;
            }

            .studio-metric strong {
                display: block;
                color: var(--studio-text);
                font-size: 1.28rem;
                line-height: 1.1;
            }

            .studio-list {
                display: grid;
                gap: 0.5rem;
                margin: 0.85rem 0 0;
                padding: 0;
                list-style: none;
            }

            .studio-list li {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                padding: 0.62rem 0.7rem;
                border-radius: 8px;
                background: #f7fbff;
                border: 1px solid #e7eefb;
                color: var(--studio-text);
            }

            .studio-list span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }

            .studio-list strong {
                color: var(--studio-blue);
                white-space: nowrap;
                font-size: 0.86rem;
            }

            .studio-next {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.65rem;
            }

            .studio-next-item {
                min-height: 92px;
                border: 1px solid var(--studio-border);
                border-radius: 8px;
                padding: 0.82rem;
                background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
            }

            .studio-next-item b {
                display: block;
                color: var(--studio-text);
                font-size: 0.92rem;
                margin-bottom: 0.32rem;
            }

            .studio-next-item small {
                color: var(--studio-muted);
                line-height: 1.45;
            }

            @media (max-width: 920px) {
                .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }

                .studio-topbar,
                .studio-dashboard {
                    display: block;
                }

                .studio-actions,
                .studio-dashboard .studio-card + .studio-card {
                    margin-top: 0.9rem;
                }

                .studio-metrics,
                .studio-next {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            @media (max-width: 560px) {
                .studio-title {
                    font-size: 1.55rem !important;
                }

                .studio-metrics,
                .studio-next {
                    grid-template-columns: 1fr;
                }

                .studio-metric {
                    border-right: 0;
                    border-bottom: 1px solid var(--studio-border);
                }

                .studio-metric:last-child {
                    border-bottom: 0;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_cloud_studio_overview(products: list[dict], database_url: str, dashscope_ready: bool) -> None:
    product_count = len(products)
    comment_count = sum(int(product.get("comment_count") or 0) for product in products)
    requirement_count = sum(int(product.get("requirement_count") or 0) for product in products)
    latest_update = str(products[0].get("updated_at", "暂无"))[:16] if products else "暂无"
    database_label = "Supabase / PostgreSQL" if not database_url.startswith("sqlite") else f"本地 SQLite / {DEFAULT_DB_PATH.name}"
    dashscope_label = "已启用" if dashscope_ready else "待配置"
    dashscope_class = "is-live" if dashscope_ready else ""
    db_class = "is-live" if not database_url.startswith("sqlite") else ""
    recent_rows = "".join(
        f"<li><span>{escape(str(product.get('name', '未命名产品')))}</span><strong>{format_number(product.get('comment_count'))} 条评论</strong></li>"
        for product in products[:5]
    )
    if not recent_rows:
        recent_rows = "<li><span>暂无产品资产</span><strong>先导入评论</strong></li>"

    st.markdown(
        f"""
        <section class="cloud-studio-shell">
            <div class="studio-topbar">
                <div class="studio-brand">
                    <div class="studio-logo">AI</div>
                    <div>
                        <h1 class="studio-title">产品评论知识库智能体</h1>
                        <div class="studio-subtitle">导入评论数据 -> 检索历史证据 -> 生成设计方案与写实渲染提示词。</div>
                    </div>
                </div>
                <div class="studio-actions">
                    <span class="studio-pill {db_class}">{escape(database_label)}</span>
                    <span class="studio-pill {dashscope_class}">阿里云写实渲染：{dashscope_label}</span>
                </div>
            </div>
            <div class="studio-flow">
                <div class="studio-step"><span>1</span>导入评论资产</div>
                <div class="studio-step"><span>2</span>需求生成</div>
                <div class="studio-step"><span>3</span>知识库概览</div>
                <div class="studio-step"><span>4</span>评论分析模块</div>
                <div class="studio-step"><span>5</span>设计方案与图片</div>
            </div>
            <div class="studio-dashboard">
                <div class="studio-card">
                    <h2 class="studio-card-title">知识库概览</h2>
                    <div class="studio-metrics">
                        <div class="studio-metric"><small>产品资产</small><strong>{format_number(product_count)}</strong></div>
                        <div class="studio-metric"><small>评论沉淀</small><strong>{format_number(comment_count)}</strong></div>
                        <div class="studio-metric"><small>需求证据</small><strong>{format_number(requirement_count)}</strong></div>
                        <div class="studio-metric"><small>最近更新</small><strong>{escape(latest_update)}</strong></div>
                    </div>
                    <ul class="studio-list">{recent_rows}</ul>
                </div>
                <div class="studio-card">
                    <h2 class="studio-card-title">下一步动作</h2>
                    <div class="studio-next">
                        <div class="studio-next-item"><b>导入</b><small>把新产品评论继续沉淀进同一个知识库。</small></div>
                        <div class="studio-next-item"><b>生成</b><small>输入新产品需求，调用历史证据生成方案。</small></div>
                        <div class="studio-next-item"><b>分析</b><small>查看清洗、关键词、情感、聚类和映射结果。</small></div>
                        <div class="studio-next-item"><b>渲染</b><small>保留 DashScope 写实效果图 API 入口。</small></div>
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_main_result_preview(
    package: dict | None,
    context: dict | None,
    dashscope_api_key: str,
    image_model: str,
    button_key: str = "main_result_preview_render",
) -> None:
    st.header("结果预览")

    if not package:
        st.info("还没有本次生成结果。请先进入“需求生成”生成一个方案。")
        st.caption("生成后这里会固定展示设计方案、prompt 和 6 张效果图预览。")
        return

    left, right = st.columns([0.6, 0.4])
    with left:
        st.subheader("设计方案预览")
        st.markdown(package.get("design_text", ""))
        with st.expander("查看引用证据和合理性检查", expanded=False):
            render_quality_report(package)
            if context:
                evidence_rows = []
                for item in context.get("requirements", [])[:5]:
                    evidence_rows.append({"类型": "需求", "来源产品": item.get("product_name", ""), "内容": item.get("title", ""), "证据": item.get("evidence_text", "")})
                for item in context.get("comments", [])[:5]:
                    evidence_rows.append({"类型": "评论", "来源产品": item.get("product_name", ""), "内容": item.get("comment_original", ""), "证据": ""})
                st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)

    with right:
        render_prompt_gallery(package, dashscope_api_key, image_model, button_key)


st.set_page_config(page_title="产品评论知识库智能体", page_icon="🧠", layout="wide")
inject_cloud_studio_theme()
database_url = get_database_url()
st.session_state.setdefault("dashscope_api_key_shared", "")

with st.sidebar:
    st.title("🧠 知识库控制台")
    st.caption(f"运行版本：{APP_VERSION}")
    owner_id = st.text_input("私人库 ID", value="private", help="当前先给你个人使用；后期共享时可扩展为登录用户 ID。")
    if database_url.startswith("sqlite"):
        st.info(f"当前使用本地 SQLite：{DEFAULT_DB_PATH.name}")
    else:
        st.success("当前使用云数据库 PostgreSQL/Supabase。")

    with st.expander("☁️ Supabase/PostgreSQL 配置", expanded=False):
        st.caption("在 Streamlit Secrets 中配置 PRODUCT_KB_DATABASE_URL 或 DATABASE_URL。没有配置时自动使用本地 SQLite。")
        st.code('PRODUCT_KB_DATABASE_URL = "postgresql://user:password@host:5432/postgres"', language="toml")

    st.divider()
    st.subheader("🎨 阿里云写实渲染")
    runtime_dashscope_key = st.text_input(
        "阿里云百炼 API Key",
        type="password",
        key="dashscope_api_key_shared",
        placeholder="sk-...",
        help="仅当前会话使用，不写入代码。也可在 Secrets 配置 DASHSCOPE_API_KEY。",
    )
    image_model = st.selectbox("图片模型", IMAGE_MODEL_OPTIONS, index=0)
    configured_dashscope_key = runtime_dashscope_key or get_secret("DASHSCOPE_API_KEY") or get_secret("QWEN_IMAGE_API_KEY")
    if configured_dashscope_key:
        st.success(f"写实渲染入口已启用：DashScope / {image_model}")
    else:
        st.caption("未填写 Key 时只生成可复制的写实渲染提示词。")


kb = get_kb(database_url, owner_id)
products = kb.list_products()

render_cloud_studio_overview(products, database_url, bool(configured_dashscope_key))

(
    tab_import,
    tab_generate,
    tab_result,
    tab_library,
    tab_downloads,
    tab_legacy,
) = st.tabs([
    "导入评论资产",
    "需求生成",
    "结果预览",
    "知识库概览",
    "📥 下载中心",
    "旧版结果",
])

with tab_import:
    st.header("导入评论资产")
    latest_import_report = st.session_state.get("latest_import_report")
    if latest_import_report:
        st.success(
            "最近一次导入完成："
            f"新增 {latest_import_report.get('inserted_count', 0)} 条，"
            f"跳过重复 {latest_import_report.get('duplicate_total', 0)} 条，"
            f"生成 {latest_import_report.get('requirement_count', 0)} 条需求证据。"
        )
        report_cols = st.columns(5)
        report_cols[0].metric("上传行数", format_number(latest_import_report.get("input_count", 0)))
        report_cols[1].metric("有效评论", format_number(latest_import_report.get("valid_count", 0)))
        report_cols[2].metric("新增入库", format_number(latest_import_report.get("inserted_count", 0)))
        report_cols[3].metric("文件内重复", format_number(latest_import_report.get("duplicate_in_file_count", 0)))
        report_cols[4].metric("库内重复", format_number(latest_import_report.get("duplicate_existing_count", 0)))

    col_left, col_right = st.columns([0.38, 0.62])
    uploaded_df = pd.DataFrame()
    selected_comment_col = ""
    preview_comments: list[str] = []
    with col_left:
        product_name = st.text_input("产品名称", placeholder="例如：智能药盒、保温杯、蓝牙耳机")
        category = st.text_input("产品品类", placeholder="例如：适老健康、厨房电器、可穿戴设备")
        uploaded = st.file_uploader("上传评论数据", type=["xlsx", "xls", "csv"])
        if uploaded is not None:
            try:
                with st.spinner("正在读取并解析上传文件..."):
                    uploaded_df = load_uploaded_table(uploaded)
                column_options = candidate_comment_columns(uploaded_df)
                suggested_col = default_comment_column(uploaded_df)
                selected_comment_col = st.selectbox(
                    "选择评论列",
                    column_options,
                    index=column_options.index(suggested_col) if suggested_col in column_options else 0,
                )
                preview_comments = extract_comments(uploaded_df, selected_comment_col)
            except Exception as exc:
                st.error(f"读取上传文件失败：{exc}")
        import_clicked = st.button(
            "存入知识库",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None or not product_name.strip() or not selected_comment_col,
        )
    with col_right:
        st.info("导入后会保存原始评论，并自动抽取一批基础需求标签。后续生成新产品时，会从这些历史评论和需求证据中检索相关内容。")
        if uploaded is not None and not uploaded_df.empty and selected_comment_col:
            st.caption(f"当前评论列：{selected_comment_col}，有效评论 {len(preview_comments)} 条")
            st.dataframe(pd.DataFrame({"评论预览": preview_comments[:20]}), use_container_width=True, hide_index=True)
        elif uploaded is None:
            st.caption("上传 CSV 或 Excel 后，可以在左侧选择评论列并预览前 20 条。")

    if import_clicked:
        if not preview_comments:
            st.error("没有可导入的评论。")
        else:
            with st.status("正在导入评论资产...", expanded=True) as import_status:
                progress = st.progress(0)
                st.write("1/4 正在校验评论列和有效评论...")
                progress.progress(15)
                with st.spinner("正在写入云数据库..."):
                    report = kb.ingest_comment_batch_with_report(product_name, category, uploaded.name, preview_comments)
                progress.progress(65)
                with st.spinner("正在抽取基础需求证据..."):
                    requirement_count = derive_requirements_from_comments(int(report["product_id"]), int(report["batch_id"]), preview_comments, kb)
                progress.progress(90)
                st.write("4/4 正在刷新知识库概览...")
                report["requirement_count"] = requirement_count
                report["selected_comment_column"] = selected_comment_col
                st.session_state["latest_import_report"] = report
                st.cache_resource.clear()
                progress.progress(100)
                import_status.update(label="评论资产导入完成", state="complete", expanded=False)
            st.rerun()

with tab_generate:
    st.header("只输入需求，生成产品方案")
    target_product = st.text_input("要生成的产品", placeholder="例如：适合老年人的智能水杯")
    demand_text = st.text_area("需求描述", placeholder="例如：提醒喝水和吃药，字体要大，操作简单，适合父母日常使用。", height=120)
    generate_clicked = st.button("从知识库生成方案", type="primary", use_container_width=True, disabled=not target_product.strip())

    if generate_clicked:
        with st.spinner("正在检索知识库并生成方案..."):
            query = f"{target_product} {demand_text}"
            context = kb.search_context(query, limit=8)
            package = generate_design_package(target_product, demand_text, context)
            context = as_plain_json(context)
            package = as_plain_json(package)
            try:
                run_id = kb.save_generation_run(target_product, demand_text, context, package)
            except Exception as exc:
                st.warning(f"生成结果已展示，但生成记录保存失败：{exc}")
                run_id = 0
        st.session_state["latest_generation"] = package
        st.session_state["latest_context"] = context
        st.session_state["latest_run_id"] = run_id
        st.session_state["latest_image_paths"] = []
        st.session_state.pop("latest_image_path", None)

    package = st.session_state.get("latest_generation")
    context = st.session_state.get("latest_context")
    if package:
        left, right = st.columns([0.62, 0.38])
        with left:
            st.subheader("设计方案")
            st.markdown(package["design_text"])
        with right:
            st.subheader("验证结果")
            render_quality_report(package)
            if context:
                st.subheader("引用证据")
                evidence_rows = []
                for item in context.get("requirements", [])[:5]:
                    evidence_rows.append({"类型": "需求", "来源产品": item.get("product_name", ""), "内容": item.get("title", ""), "证据": item.get("evidence_text", "")})
                for item in context.get("comments", [])[:5]:
                    evidence_rows.append({"类型": "评论", "来源产品": item.get("product_name", ""), "内容": item.get("comment_original", ""), "证据": ""})
                st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)

            render_prompt_gallery(package, configured_dashscope_key, image_model, "generate_tab_render_all")

with tab_result:
    render_main_result_preview(
        st.session_state.get("latest_generation"),
        st.session_state.get("latest_context"),
        configured_dashscope_key,
        image_model,
    )

with tab_library:
    st.header("知识库概览")
    if products:
        product_df = pd.DataFrame(products).rename(
            columns={
                "id": "ID",
                "name": "产品名称",
                "category": "产品品类",
                "description": "备注",
                "comment_count": "评论数",
                "requirement_count": "需求证据数",
                "created_at": "创建时间",
                "updated_at": "更新时间",
            }
        )
        visible_columns = ["ID", "产品名称", "产品品类", "评论数", "需求证据数", "更新时间"]
        st.dataframe(product_df[visible_columns], use_container_width=True, hide_index=True)

        st.subheader("产品管理")
        selected_product_label = st.selectbox(
            "选择要管理的产品",
            [f"{product['id']} · {product['name']}" for product in products],
        )
        selected_product_id = int(selected_product_label.split(" · ", 1)[0])
        selected_product = next(product for product in products if int(product["id"]) == selected_product_id)

        edit_left, edit_right = st.columns([0.5, 0.5])
        with edit_left:
            edited_name = st.text_input("产品名称", value=str(selected_product.get("name") or ""), key=f"edit_product_name_{selected_product_id}")
        with edit_right:
            edited_category = st.text_input("产品品类", value=str(selected_product.get("category") or ""), key=f"edit_product_category_{selected_product_id}")
        edited_description = st.text_area(
            "备注",
            value=str(selected_product.get("description") or ""),
            height=80,
            key=f"edit_product_description_{selected_product_id}",
        )
        save_product_clicked = st.button(
            "保存产品信息",
            type="primary",
            use_container_width=True,
            disabled=not edited_name.strip(),
        )
        if save_product_clicked:
            try:
                if kb.update_product(selected_product_id, edited_name, edited_category, edited_description):
                    st.success("产品信息已更新。")
                    st.cache_resource.clear()
                    st.rerun()
                else:
                    st.warning("没有找到要更新的产品。")
            except Exception as exc:
                st.error(f"更新失败：{exc}")

        with st.expander("删除产品数据", expanded=False):
            st.warning("删除后会移除该产品、评论批次、评论和需求证据。已生成记录不会自动删除。")
            delete_confirm = st.text_input(
                f"如需删除，请输入产品名称：{selected_product['name']}",
                key=f"delete_confirm_{selected_product_id}",
            )
            delete_clicked = st.button(
                "确认删除该产品",
                use_container_width=True,
                disabled=delete_confirm != selected_product["name"],
                key=f"delete_product_{selected_product_id}",
            )
            if delete_clicked:
                if kb.delete_product(selected_product_id):
                    st.success("产品及关联评论数据已删除。")
                    st.cache_resource.clear()
                    st.rerun()
                else:
                    st.warning("没有找到要删除的产品。")
    else:
        st.info("知识库还没有评论资产，请先导入至少一个产品的评论数据。")

with tab_downloads:
    st.header("下载中心")
    package = st.session_state.get("latest_generation")
    current_image_paths = get_latest_image_paths()
    if package:
        st.subheader("本次生成")
        st.download_button(
            "下载本次设计方案",
            data=str(package.get("design_text", "")).encode("utf-8"),
            file_name=f"{package.get('target_product', 'product')}_设计方案.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_current_design_text",
        )
        prompt_text = "\n\n".join(f"prompt {index}\n{prompt}" for index, prompt in enumerate(get_image_prompts(package), start=1))
        st.download_button(
            "下载本次生成 prompt",
            data=prompt_text.encode("utf-8"),
            file_name=f"{package.get('target_product', 'product')}_prompts.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_current_prompts",
        )
        render_image_download_grid(current_image_paths, "download_center_current")
        st.divider()

    download_files = [
        "cleaned_comments.xlsx",
        "需求关键词提取结果.xlsx",
        "情感分析结果.xlsx",
        "BERTopic主题聚类结果.xlsx",
        "neo4j_nodes.csv",
        "neo4j_relationships.csv",
        "import_neo4j.cypher",
        "需求—功能—结构映射表.xlsx",
        "AI生成参数表.xlsx",
        "ai_generation_parameters.json",
        "prompt_template.txt",
        "方案评价表.xlsx",
        "方案评价结果.json",
        "方案优化建议.txt",
        "优化后AI生成参数.json",
        "开题报告实验结果摘要.docx",
    ]
    mapping_files = sorted(path.name for path in LEGACY_OUTPUT_DIR.glob("*_需求功能映射数据库.xlsx"))
    scheme_files = sorted(path.name for path in LEGACY_OUTPUT_DIR.glob("*产品设计方案.*"))
    found = False
    for rel_path in mapping_files + scheme_files + download_files:
        path = LEGACY_OUTPUT_DIR / rel_path
        if path.exists() and path.is_file():
            found = True
            show_legacy_file_download(rel_path)
    if not found:
        st.info("还没有可下载的完整流程结果。可在“旧版入口”运行后返回这里下载。")

with tab_legacy:
    st.header("旧版模块已拆到独立页面")
    st.write("查看旧版清洗、关键词、情感、主题、图谱、设计图片和评价结果：左侧页面导航 `03_旧版结果预览`。")
    st.write("运行旧版完整流程：左侧页面导航 `01_现有流程备份`。")
    st.write("本地也可以单独运行：")
    st.code("streamlit run app_legacy_current.py", language="bash")
