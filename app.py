from __future__ import annotations

import importlib.util
import inspect
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
import streamlit.components.v1 as components

from scripts.common import build_cleaned_dataframe
from scripts.product_knowledge_base import (
    DEFAULT_DB_PATH,
    ProductKnowledgeBase,
    generate_design_package,
    normalize_database_url,
)
from scripts.upload_parsing import candidate_comment_columns, default_comment_column, extract_comments, read_upload_table
from scripts.visual_asset_quality import evaluate_visual_asset


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output" / "knowledge_runs"
LEGACY_OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_IMAGE_MODEL = "qwen-image-2.0-pro-2026-06-22"
APP_VERSION = "2026-07-13-provider-error-details-v9"
MAX_VISUAL_RETRIES = 2
IMAGE_MODEL_OPTIONS = [
    DEFAULT_IMAGE_MODEL,
    "qwen-image-2.0-pro",
    "qwen-image-max",
    "qwen-image-plus",
    "wan2.2-t2i-plus",
]
OPENAI_IMAGE_MODEL_OPTIONS = [
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1-mini",
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


def describe_database_startup_error(database_url: str, error: Exception) -> str:
    """Return an actionable, non-sensitive database startup diagnosis for the UI."""
    if database_url.startswith("sqlite"):
        return "本地知识库无法初始化，请检查磁盘写入权限或数据库文件。"

    error_name = type(error).__name__
    message = str(error).lower()
    if "password authentication failed" in message or "authentication failed" in message:
        return "云数据库认证失败，请在 Streamlit Secrets 中检查连接串中的用户名和密码。"
    if "could not translate host name" in message or "name or service not known" in message:
        return "云数据库地址无法解析，请检查连接串中的主机地址。"
    if "connection refused" in message or "timeout" in message or "timed out" in message:
        return "云数据库无法建立连接，请检查 Supabase 项目状态、连接端口和网络访问。"
    if "psycopg" in message or error_name == "ImportError":
        return "云数据库驱动未就绪，部署会自动安装 psycopg[binary] 后重试。"
    return f"云数据库初始化失败（{error_name}）。请在 Streamlit Cloud 的应用日志中检查数据库连接配置。"


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


def build_openai_config(api_key: str, model: str) -> dict:
    return {
        "provider": "openai",
        "api_key": api_key,
        "base_url": os.getenv("OPENAI_IMAGE_BASE_URL") or None,
        "task_url": "",
        "model": model,
        "quality": "high",
        "custom_base_url": bool(os.getenv("OPENAI_IMAGE_BASE_URL")),
    }


def visual_asset_output_path(target_product: str, asset: dict, image_index: int) -> Path:
    safe_name = "".join(char if char.isalnum() or "\u4e00" <= char <= "\u9fff" else "_" for char in target_product)[:40] or "product"
    image_dir = OUTPUT_DIR / "dashscope_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    asset_key = str(asset.get("key") or f"image_{image_index:02d}")
    asset_label = str(asset.get("label") or f"效果图{image_index}")
    return image_dir / f"{safe_name}_{image_index:02d}_{asset_key}_{asset_label}.png"


def generate_image_render(
    prompt: str,
    target_product: str,
    image_config: dict,
    image_index: int = 1,
    asset: dict | None = None,
    reference_image: Path | None = None,
) -> Path | None:
    if not image_config.get("api_key"):
        return None
    module = load_design_visuals_module()
    asset = asset or {"key": f"image_{image_index:02d}", "label": f"效果图{image_index}", "size": "1024x1024"}
    output_path = visual_asset_output_path(target_product, asset, image_index)
    render_config = {**image_config, "strict_reference": reference_image is not None}
    ok = module.generate_ai_image(
        prompt,
        output_path,
        size=str(asset.get("size") or "1024x1024"),
        reference_path=reference_image,
        config=render_config,
    )
    if not ok:
        provider_error = module.format_image_generation_errors(module.IMAGE_GENERATION_EVENTS)
        if provider_error:
            image_config.setdefault("_provider_errors", []).append(provider_error)
    return output_path if ok and output_path.exists() else None


def build_reference_locked_prompt(prompt: str, asset: dict, has_reference: bool) -> str:
    key = str(asset.get("key") or "")
    asset_label = str(asset.get("label") or "产品视图")
    reference_rule = (
        "输入参考图是唯一产品母版。必须复用其中完全相同的外轮廓、上盖、分格数量、屏幕位置、按键位置、主色、材料和比例；"
        "只允许改变镜头、拆解方式或真实使用场景，绝不允许重新设计另一款产品。"
        if has_reference
        else "本图将作为唯一产品母版。必须只输出一款完整产品，居中且占画面主体。"
    )
    layout_rule = (
        "三视图仅允许正视、侧视、俯视三个正交工程视图，比例必须一致，不能出现产品变体。"
        if key == "three_view"
        else "严格只输出一张单画面，不得制作九宫格、拼贴、分屏、接触表、多个角度合集、多个方案或产品变体。"
    )
    distinct_rule = (
        "第二张产品效果图必须使用与产品效果图 1 不同的镜头构图、机位高度和光影关系，但产品本体必须完全一致。"
        if key == "render_2"
        else "第二张使用效果图必须使用与产品使用效果图 1 不同的使用动作或场景构图，但产品本体必须完全一致。"
        if key == "usage_2"
        else ""
    )
    return (
        f"视觉一致性硬约束：{reference_rule} 图像类型：{asset_label}。{layout_rule} {distinct_rule} "
        "若无法保持同一产品，请不要替换设计。no collage, no contact sheet, no multi-panel, no product variations.\n\n"
        f"{prompt}"
    )


def validate_visual_asset(
    image_path: Path,
    asset: dict,
    reference_image: Path | None = None,
) -> dict[str, object]:
    return evaluate_visual_asset(
        image_path,
        str(asset.get("key") or ""),
        reference_image=reference_image,
    )


def package_visual_identity_lock(package: dict) -> str:
    product_name = str(package.get("target_product") or "product")
    demand_text = str(package.get("demand_text") or product_name)
    guard = (
        "固定为同一款智能分格药盒：圆角矩形盒体、半透明或透明上盖、清晰药格、前置提醒屏或指示灯、药片分区明确；"
        "不得生成耳机盒、充电盒、蓝牙耳机、化妆盒、首饰盒、普通收纳盒或多方案拼贴。"
        if "药盒" in product_name
        else f"固定为同一款{product_name}，不得生成其他品类、替代产品、多方案拼贴或无关对象。"
    )
    return (
        f"统一产品设计锁定：所有设计图片必须表现同一款“{product_name}”，只能改变镜头视角、拆解方式、展板排版和使用场景，"
        "不得改变产品本体；保持同一轮廓、同一主色、同一材料质感、同一关键部件数量、同一尺寸比例、同一操作区域。"
        f"目标需求：{demand_text}。负向约束：{guard} "
        "photorealistic industrial design visualization, no logo, no watermark, no collage, no contact sheet, no unrelated object."
    )


def build_visual_assets_from_package(package: dict) -> list[dict]:
    product_name = str(package.get("target_product") or "product")
    identity_lock = package_visual_identity_lock(package)
    industrial_design_prompt = str(package.get("industrial_design_prompt") or "").strip()
    templates = [
        ("render_1", "产品效果图 1", "1024x1024", "单张专业产品效果图，45度主视角，单一产品主体，白色或浅灰干净背景，真实PBR材质、圆角、阴影、高光和核心交互区清晰可见；不是拼图，不是九宫格。"),
        ("render_2", "产品效果图 2", "1024x1024", "单张专业产品效果图，从略高的30度侧前方观察同一款产品，展示上盖、主控区和分格结构；不是拼图，不是九宫格。"),
        ("exploded", "产品爆炸图", "1024x1792", "单张立体写实爆炸图：等距轴测视角，所有同款产品零部件沿中心垂直装配轴从上到下真实分离并分层悬浮；部件必须有厚度、圆角、透视、真实阴影和 PBR 材质高光。展示外壳、功能模块、内部空间、连接件、可维护部件和装配关系；不是平面示意图、不是多宫格、不是拼贴图、不是另一款产品。"),
        ("detail", "产品细节图", "1024x1024", "产品细节特写图，只放大同一款产品上的关键结构、材质、开启方式、按键、屏幕、提示灯或连接细节，微距摄影质感。"),
        ("three_view", "产品三视图", "1792x1024", "工业设计三视图，同一产品以统一比例展示正视图、侧视图和俯视图，严格对齐，白色背景，无透视变形，适合工程表达。"),
        ("board", "设计展板", "1600x2200", "设计展板，整合产品效果图、爆炸图、细节图、三视图、使用效果图、需求分析和功能结构映射；信息层级清晰，少文字，多图像，适合论文和开题展示。"),
        ("usage_1", "产品使用效果图 1", "1024x1024", "单张真实使用场景图，目标用户在自然生活环境中使用同一款产品，人物动作、产品尺度、空间关系和核心功能表达真实合理；不是拼图，不是九宫格。"),
        ("usage_2", "产品使用效果图 2", "1024x1024", "单张真实使用场景图，从另一自然视角展示同一款产品被目标用户操作或提醒，产品轮廓、材料、分格数量和核心交互区必须与母版完全一致；不是拼图，不是九宫格。"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "size": size,
            "prompt": f"{identity_lock}\n\n{industrial_design_prompt}\n\n图像任务 {index}：{label}。{prompt} 产品名称必须明确是{product_name}，画面只服务于当前这一款产品。",
        }
        for index, (key, label, size, prompt) in enumerate(templates, start=1)
    ]


def get_visual_assets(package: dict | None) -> list[dict]:
    if not package:
        return []
    visual_assets = package.get("visual_assets") or []
    valid_assets = [asset for asset in visual_assets if str(asset.get("prompt", "")).strip()]
    valid_keys = {str(asset.get("key") or "") for asset in valid_assets}
    if len(valid_assets) >= 8 and {"render_1", "render_2", "usage_1", "usage_2"}.issubset(valid_keys):
        return valid_assets[:8]
    return build_visual_assets_from_package(package)


def get_image_prompts(package: dict | None) -> list[str]:
    if not package:
        return []
    prompts = package.get("image_prompts") or []
    if not prompts and package.get("image_prompt_text"):
        prompts = [package["image_prompt_text"]]
    return [str(prompt).strip() for prompt in prompts if str(prompt).strip()][:8]


def package_visual_frames(package: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    report = package.get("quality_report", {}) if isinstance(package, dict) else {}
    checks = report.get("checks", []) if isinstance(report, dict) else []
    req_df = pd.DataFrame(
        [
            {
                "需求主题": str(package.get("demand_text") or package.get("target_product") or "产品需求"),
                "需求描述": str(package.get("demand_text") or ""),
                "来源关键词": "、".join(str(item) for item in checks[:4]),
            }
        ]
    )
    topic_df = pd.DataFrame([{"主题关键词": "、".join(str(item) for item in checks[:6])}])
    return req_df, topic_df


def create_visual_fallback(module, package: dict, asset: dict, output_path: Path, generated_paths: dict[str, Path]) -> None:
    product_name = str(package.get("target_product") or "product")
    req_df, topic_df = package_visual_frames(package)
    empty_struct = pd.DataFrame()
    key = str(asset.get("key") or "")
    label = str(asset.get("label") or "效果图")
    if key.startswith("render"):
        module.create_product_identity_reference_image(output_path, product_name)
    elif key == "exploded":
        module.create_exploded_schematic(output_path, product_name, empty_struct)
    elif key == "three_view":
        module.create_three_view_placeholder(output_path, product_name)
    elif key == "board":
        images = {
            "render": generated_paths.get("render_1", output_path),
            "exploded": generated_paths.get("exploded", output_path),
            "detail": generated_paths.get("detail", generated_paths.get("render_1", output_path)),
            "three_view": generated_paths.get("three_view", output_path),
            "usage": generated_paths.get("usage_1", generated_paths.get("render_1", output_path)),
            "board": output_path,
        }
        module.create_board(output_path, images, req_df, topic_df, product_name)
    else:
        module.create_simple_placeholder(output_path, f"{product_name} {label}")


def _generate_visual_asset_set_legacy(
    package: dict,
    image_config: dict,
    progress,
    status,
) -> list[Path]:
    module = load_design_visuals_module()
    assets = get_visual_assets(package)
    product_name = str(package.get("target_product") or "product")
    generated_paths: dict[str, Path] = {}
    reference_image: Path | None = None
    board_asset: tuple[int, dict] | None = None
    for index, asset in enumerate(assets, start=1):
        key = str(asset.get("key") or "")
        label = str(asset.get("label") or f"效果图{index}")
        output_path = visual_asset_output_path(product_name, asset, index)
        if key == "board":
            board_asset = (index, asset)
            progress.progress(int(index / max(len(assets), 1) * 100))
            continue
        if key == "exploded":
            status.write(f"图像服务生成第 {index}/{len(assets)} 张：单张立体写实爆炸图...")
        else:
            status.write(f"图像服务生成第 {index}/{len(assets)} 张：{label}...")
        generated_image_path = generate_image_render(
            str(asset.get("prompt", "")),
            product_name,
            image_config,
            index,
            asset=asset,
            reference_image=reference_image,
        )
        if generated_image_path:
            output_path = generated_image_path
        else:
            create_visual_fallback(module, package, asset, output_path, generated_paths)
        if output_path.exists():
            generated_paths[key or f"image_{index}"] = output_path
            if key == "render":
                reference_image = output_path
        progress.progress(int(index / max(len(assets), 1) * 100))
    if board_asset:
        index, asset = board_asset
        label = str(asset.get("label") or "设计展板")
        status.write(f"正在合成第 {index}/{len(assets)} 张：{label}...")
        output_path = visual_asset_output_path(product_name, asset, index)
        create_visual_fallback(module, package, asset, output_path, generated_paths)
        if output_path.exists():
            generated_paths[str(asset.get("key") or "board")] = output_path
        progress.progress(100)
    return [generated_paths[str(asset.get("key") or f"image_{index}")] for index, asset in enumerate(assets, start=1) if str(asset.get("key") or f"image_{index}") in generated_paths]


def generate_visual_asset_set(
    package: dict,
    image_config: dict,
    progress,
    status,
) -> tuple[list[Path], list[str]]:
    """Generate an 8-view package and reject output that fails visual QA."""
    image_config.pop("_provider_errors", None)
    module = load_design_visuals_module()
    assets = get_visual_assets(package)
    product_name = str(package.get("target_product") or "product")
    generated_paths: dict[str, Path] = {}
    failures: list[str] = []
    reference_image: Path | None = None
    board_asset: tuple[int, dict] | None = None

    for index, asset in enumerate(assets, start=1):
        key = str(asset.get("key") or f"image_{index}")
        label = str(asset.get("label") or f"效果图 {index}")
        if key == "board":
            board_asset = (index, asset)
            continue

        output_path = visual_asset_output_path(product_name, asset, index)
        accepted_path: Path | None = None
        final_reason = "图像服务未返回可验收图片"
        for attempt in range(1, MAX_VISUAL_RETRIES + 1):
            if output_path.exists():
                output_path.unlink()
            status.write(f"正在生成并验收第 {index}/{len(assets)} 张：{label}（第 {attempt}/{MAX_VISUAL_RETRIES} 次）...")
            prompt = build_reference_locked_prompt(
                str(asset.get("prompt", "")),
                asset,
                has_reference=reference_image is not None,
            )
            generated_image_path = generate_image_render(
                prompt,
                product_name,
                image_config,
                index,
                asset=asset,
                reference_image=reference_image,
            )
            if not generated_image_path:
                final_reason = "图像服务未返回图片，请检查模型权限、余额或网络"
                continue

            distinct_reference = (
                generated_paths.get("render_1")
                if key == "render_2"
                else generated_paths.get("usage_1")
                if key == "usage_2"
                else None
            )
            result = validate_visual_asset(
                generated_image_path,
                asset,
                reference_image=distinct_reference,
            )
            if result.get("accepted"):
                accepted_path = generated_image_path
                break
            final_reason = str(result.get("reason") or "视觉验收未通过")

        if not accepted_path:
            failures.append(f"{label}：{final_reason}")
            progress.progress(int(index / max(len(assets), 1) * 100))
            continue

        generated_paths[key] = accepted_path
        if key == "render_1":
            reference_image = accepted_path
        progress.progress(int(index / max(len(assets), 1) * 100))

    required_keys = [str(asset.get("key") or "") for asset in assets if str(asset.get("key") or "") != "board"]
    if reference_image is None:
        failures.append("产品效果图 1：未生成可用母版，后续视图无法保证一致性")
    for key in required_keys:
        if key and key not in generated_paths:
            asset = next((item for item in assets if str(item.get("key") or "") == key), {})
            label = str(asset.get("label") or key)
            if not any(item.startswith(f"{label}：") for item in failures):
                failures.append(f"{label}：未通过视觉一致性验收")
    if failures:
        return [], failures

    if board_asset:
        index, asset = board_asset
        status.write(f"正在合成第 {index}/{len(assets)} 张：{asset.get('label', '设计展板')}...")
        output_path = visual_asset_output_path(product_name, asset, index)
        if output_path.exists():
            output_path.unlink()
        create_visual_fallback(module, package, asset, output_path, generated_paths)
        board_result = validate_visual_asset(output_path, asset)
        if not board_result.get("accepted"):
            return [], [f"设计展板：{board_result.get('reason', '视觉验收未通过')}"]
        generated_paths[str(asset.get("key") or "board")] = output_path
    progress.progress(100)
    ordered_paths = [
        generated_paths[str(asset.get("key") or f"image_{index}")]
        for index, asset in enumerate(assets, start=1)
        if str(asset.get("key") or f"image_{index}") in generated_paths
    ]
    return ordered_paths, []


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
    return paths[:8]


def store_latest_image_paths(paths: list[Path]) -> None:
    current = [str(path) for path in paths[:8] if path.exists()]
    st.session_state["latest_image_paths"] = current
    if current:
        st.session_state["latest_image_path"] = current[0]


def render_image_download_grid(image_paths: list[Path], key_prefix: str, assets: list[dict] | None = None) -> None:
    if not image_paths:
        st.info("还没有效果图。可以生成 8 张独立设计图，或复制 prompt 到其他生图工具。")
        return
    assets = assets or []
    columns = st.columns(3)
    for index, image_path in enumerate(image_paths[:8], start=1):
        label = str(assets[index - 1].get("label")) if index - 1 < len(assets) else f"效果图 {index}"
        with columns[(index - 1) % 3]:
            st.image(str(image_path), caption=label, use_container_width=True)
            st.download_button(
                f"下载本次效果图：{label}",
                data=image_path.read_bytes(),
                file_name=image_path.name,
                mime="image/png",
                use_container_width=True,
                key=f"{key_prefix}_image_download_{index}",
            )


def build_all_prompts_text(assets: list[dict]) -> str:
    return "\n\n".join(
        f"prompt {index} · {asset.get('label', '效果图')}\n{str(asset.get('prompt') or '').strip()}"
        for index, asset in enumerate(assets, start=1)
        if str(asset.get("prompt") or "").strip()
    )


def render_copy_all_prompts_button(prompt_text: str, key: str) -> None:
    payload = json.dumps(prompt_text, ensure_ascii=False).replace("</", "<\\/")
    button_id = f"copy-all-prompts-{key}".replace("_", "-")
    html = f"""
        <button id="{button_id}" style="width:100%;height:38px;border:1px solid #c9daf8;border-radius:8px;background:#fff;color:#17345f;font-weight:650;cursor:pointer;">复制全部 prompt</button>
        <script>
          const button = document.getElementById({json.dumps(button_id)});
          const promptText = {payload};
          button.addEventListener('click', async () => {{
            try {{
              await navigator.clipboard.writeText(promptText);
              button.textContent = '已复制全部 prompt';
              setTimeout(() => button.textContent = '复制全部 prompt', 1600);
            }} catch (error) {{
              button.textContent = '复制失败，请使用每条 prompt 的复制图标';
            }}
          }});
        </script>
        """
    if hasattr(st, "html") and "unsafe_allow_javascript" in inspect.signature(st.html).parameters:
        st.html(html, unsafe_allow_javascript=True)
    else:
        components.html(html, height=46)


def _render_prompt_gallery_legacy(package: dict, image_config: dict, render_provider: str, button_key: str) -> None:
    assets = get_visual_assets(package)
    prompts = [str(asset.get("prompt", "")).strip() for asset in assets if str(asset.get("prompt", "")).strip()]
    st.subheader("prompt")
    if assets:
        render_copy_all_prompts_button(build_all_prompts_text(assets), f"{button_key}_all_prompts")
        for index, asset in enumerate(assets, start=1):
            st.markdown(f"**prompt {index} · {asset.get('label', '效果图')}**")
            prompt = str(asset.get("prompt", "")).strip()
            st.code(prompt, language="text")
    else:
        st.info("当前方案还没有 prompt。")

    st.subheader("效果图预览")
    render_image_download_grid(get_latest_image_paths(), button_key, assets)

    if st.button(f"用{render_provider}生成 {len(prompts) or 8} 张效果图", use_container_width=True, disabled=not image_config.get("api_key") or not prompts, key=button_key):
        progress = st.progress(0)
        status = st.empty()
        generated_paths, validation_failures = generate_visual_asset_set(package, image_config, progress, status)
        if generated_paths:
            store_latest_image_paths(generated_paths)
            st.success(f"视觉一致性基础验收通过，已生成 {len(generated_paths)} 张独立设计图。")
            render_image_download_grid(get_latest_image_paths(), f"{button_key}_generated", assets)
        else:
            store_latest_image_paths([])
            failure_text = "；".join(validation_failures) if validation_failures else "图像服务未返回可验收图片"
            st.error(f"视觉验收未通过：{failure_text}。不展示低质量回退图，请调整 Key、模型权限、余额或网络后重新生成。")
    elif not image_config.get("api_key"):
        st.caption(f"填写{render_provider} API Key 后可在这里直接生成 8 张独立设计图。")


def render_prompt_gallery(package: dict, image_config: dict, render_provider: str, button_key: str) -> None:
    assets = get_visual_assets(package)
    prompts = [str(asset.get("prompt", "")).strip() for asset in assets if str(asset.get("prompt", "")).strip()]
    prompt_text = build_all_prompts_text(assets)

    st.subheader("生成效果图")
    render_requested = st.button(
        f"用{render_provider}生成 {len(prompts) or 8} 张效果图",
        type="primary",
        use_container_width=True,
        key=f"{button_key}_generate_images",
    )
    if render_requested:
        if not prompts:
            st.error("当前方案没有可用于渲染的 prompt。")
        elif not image_config.get("api_key"):
            st.warning(f"当前渲染服务尚未载入 API Key。请在左侧填写{render_provider} API Key 后重试。")
        else:
            progress = st.progress(0)
            status = st.empty()
            generated_paths, validation_failures = generate_visual_asset_set(package, image_config, progress, status)
            if generated_paths:
                store_latest_image_paths(generated_paths)
                st.success(f"视觉一致性基础验收通过，已生成 {len(generated_paths)} 张独立设计图。")
            else:
                store_latest_image_paths([])
                failure_text = "；".join(validation_failures) if validation_failures else "图像服务未返回可验收图片"
                st.error(f"视觉验收未通过：{failure_text}。不展示低质量回退图，请调整 Key、模型权限、余额或网络后重新生成。")
                provider_errors = list(dict.fromkeys(image_config.get("_provider_errors", [])))
                if provider_errors:
                    error_heading = "阿里云返回的真实错误" if image_config.get("provider") == "dashscope" else "OpenAI 返回的真实错误"
                    st.error(error_heading)
                    st.code("\n\n".join(provider_errors), language="text")

    st.subheader("效果图预览")
    render_image_download_grid(get_latest_image_paths(), f"{button_key}_preview", assets)

    st.subheader("完整 8 条 prompt")
    if not assets:
        st.info("当前方案还没有 prompt。")
        return
    render_copy_all_prompts_button(prompt_text, f"{button_key}_all_prompts")
    prompt_labels = [f"prompt {index} · {asset.get('label', '效果图')}" for index, asset in enumerate(assets, start=1)]
    selected_label = st.selectbox("选择要查看的 prompt", prompt_labels, key=f"{button_key}_prompt_selector")
    selected_index = prompt_labels.index(selected_label)
    st.code(str(assets[selected_index].get("prompt") or ""), language="text")
    with st.expander("查看全部 8 条 prompt", expanded=False):
        st.code(prompt_text, language="text")


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


def render_cloud_studio_overview(products: list[dict], database_url: str, rendering_ready: bool, rendering_label: str) -> None:
    product_count = len(products)
    comment_count = sum(int(product.get("comment_count") or 0) for product in products)
    requirement_count = sum(int(product.get("requirement_count") or 0) for product in products)
    latest_update = str(products[0].get("updated_at", "暂无"))[:16] if products else "暂无"
    database_label = "Supabase / PostgreSQL" if not database_url.startswith("sqlite") else f"本地 SQLite / {DEFAULT_DB_PATH.name}"
    rendering_status = "已启用" if rendering_ready else "待配置"
    rendering_class = "is-live" if rendering_ready else ""
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
                    <span class="studio-pill {rendering_class}">写实渲染：{escape(rendering_label)} / {rendering_status}</span>
                </div>
            </div>
            <div class="studio-flow">
                <div class="studio-step"><span>1</span>导入评论资产</div>
                <div class="studio-step"><span>2</span>需求生成</div>
                <div class="studio-step"><span>3</span>知识库概览</div>
                <div class="studio-step"><span>4</span>需求-功能-结构图谱</div>
                <div class="studio-step"><span>5</span>设计方案</div>
                <div class="studio-step"><span>6</span>工业设计 Prompt</div>
                <div class="studio-step"><span>7</span>AI 图片生成</div>
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
    image_config: dict,
    render_provider: str,
    button_key: str = "main_result_preview_render",
) -> None:
    st.header("结果预览")

    if not package:
        st.info("还没有本次生成结果。请先进入“需求生成”生成一个方案。")
        st.caption("生成后这里会固定展示设计方案、prompt 和 8 张独立设计图预览。")
        return

    st.subheader("设计方案预览")
    st.markdown(package.get("design_text", ""))
    industrial_design_prompt = str(package.get("industrial_design_prompt") or "").strip()
    if industrial_design_prompt:
        with st.expander("工业设计 Prompt 约束", expanded=False):
            st.code(industrial_design_prompt, language="text")
    with st.expander("查看引用证据和合理性检查", expanded=False):
        render_quality_report(package)
        if context:
            evidence_rows = []
            for item in context.get("requirements", [])[:5]:
                evidence_rows.append({"类型": "需求", "来源产品": item.get("product_name", ""), "内容": item.get("title", ""), "证据": item.get("evidence_text", "")})
            for item in context.get("comments", [])[:5]:
                evidence_rows.append({"类型": "评论", "来源产品": item.get("product_name", ""), "内容": item.get("comment_original", ""), "证据": ""})
            st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)

    st.divider()
    render_prompt_gallery(package, image_config, render_provider, button_key)


st.set_page_config(page_title="产品评论知识库智能体", page_icon="🧠", layout="wide")
inject_cloud_studio_theme()
database_url = get_database_url()
st.session_state.setdefault("dashscope_api_key_shared", "")
st.session_state.setdefault("openai_api_key_shared", "")

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
    st.subheader("🎨 写实渲染服务")
    render_provider = st.radio("本次生成使用", ["阿里云百炼", "OpenAI"], horizontal=True)

    st.caption("阿里云入口保留；选择 OpenAI 后可优先生成单张立体写实爆炸图。两个 Key 都只保存在当前浏览器会话。")
    st.markdown("**阿里云写实渲染**")
    runtime_dashscope_key = st.text_input(
        "阿里云百炼 API Key",
        type="password",
        key="dashscope_api_key_shared",
        placeholder="sk-...",
        help="仅当前会话使用，不写入代码。也可在 Secrets 配置 DASHSCOPE_API_KEY。",
    )
    image_model = st.selectbox("图片模型", IMAGE_MODEL_OPTIONS, index=0)
    configured_dashscope_key = runtime_dashscope_key or get_secret("DASHSCOPE_API_KEY") or get_secret("QWEN_IMAGE_API_KEY")
    st.markdown("**OpenAI 写实渲染**")
    runtime_openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        key="openai_api_key_shared",
        placeholder="sk-...",
        help="仅当前会话使用，不写入代码、数据库、生成记录或下载文件。也可在 Secrets 配置 OPENAI_API_KEY。",
    )
    openai_image_model = st.selectbox("OpenAI 图片模型", OPENAI_IMAGE_MODEL_OPTIONS, index=0)
    configured_openai_key = runtime_openai_key or get_secret("OPENAI_API_KEY") or get_secret("IMAGE_API_KEY")

    if render_provider == "OpenAI":
        active_image_config = build_openai_config(configured_openai_key, openai_image_model)
        active_render_label = f"OpenAI / {openai_image_model}"
    else:
        active_image_config = build_dashscope_config(configured_dashscope_key, image_model)
        active_render_label = f"DashScope / {image_model}"
    if active_image_config.get("api_key"):
        st.success(f"写实渲染入口已启用：{active_render_label}")
    else:
        st.caption(f"请填写{render_provider} API Key；未填写时只生成可复制的写实渲染提示词。")


try:
    kb = get_kb(database_url, owner_id)
except Exception as database_error:
    st.error(describe_database_startup_error(database_url, database_error))
    if not database_url.startswith("sqlite"):
        st.info("为保护已沉淀的评论和方案数据，系统不会在云数据库异常时自动切换到临时本地数据库。")
    st.stop()

products = kb.list_products()

render_cloud_studio_overview(products, database_url, bool(active_image_config.get("api_key")), active_render_label)

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
    with st.expander("工业设计 Prompt 约束", expanded=True):
        st.caption("这些约束会写入本次方案记录，并自动附加到每一条生图 prompt。")
        constraint_left, constraint_right = st.columns(2)
        with constraint_left:
            functional_requirements = st.text_area("功能需求", placeholder="例如：定时提醒、误操作确认、手机同步", height=90)
            product_structure = st.text_area("产品结构", placeholder="例如：圆角矩形主体、透明翻盖、七个独立药仓、前置提醒屏", height=90)
            material_specification = st.text_area("材料要求", placeholder="例如：304不锈钢、ABS塑料、TPE软胶、铝合金、半透明磨砂材料", height=90)
            dimension_proportion = st.text_area("尺寸比例约束", placeholder="例如：长宽比 1.6:1，单手可握，按键直径不小于 12mm", height=90)
        with constraint_right:
            application_scenario = st.text_area("使用场景", placeholder="例如：居家养老环境，老人坐在餐桌旁使用", height=90)
            visual_style = st.text_area("视觉风格", placeholder="例如：工业设计效果图、KeyShot渲染、产品摄影、写实渲染、4K高清", height=90)
            camera_angle = st.text_area("镜头与构图", placeholder="例如：45度三分之四视角，柔和工作室布光；工程图使用正视、侧视、顶视", height=90)
            negative_constraints = st.text_area("禁止修改项", placeholder="例如：不改变产品结构，不改变尺寸比例，不增加额外功能，保持统一产品设计语言", height=90)
    industrial_constraints = {
        "product_name": target_product,
        "user_needs": demand_text,
        "functional_requirements": functional_requirements,
        "product_structure": product_structure,
        "material_specification": material_specification,
        "dimension_proportion": dimension_proportion,
        "application_scenario": application_scenario,
        "visual_style": visual_style,
        "camera_angle": camera_angle,
        "negative_constraints": negative_constraints,
    }
    generate_clicked = st.button("从知识库生成方案", type="primary", use_container_width=True)

    if generate_clicked and not target_product.strip():
        st.warning("请先填写要生成的产品。")
    elif generate_clicked:
        with st.spinner("正在检索知识库并生成方案..."):
            query = f"{target_product} {demand_text}"
            context = kb.search_context(query, limit=8)
            context = {**context, "industrial_constraints": industrial_constraints}
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
        st.success("生成完成，请切换到“结果预览”查看设计方案、完整 prompt 与效果图。")

with tab_result:
    render_main_result_preview(
        st.session_state.get("latest_generation"),
        st.session_state.get("latest_context"),
        active_image_config,
        render_provider,
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
        current_assets = get_visual_assets(package)
        st.subheader("本次生成")
        st.download_button(
            "下载本次设计方案",
            data=str(package.get("design_text", "")).encode("utf-8"),
            file_name=f"{package.get('target_product', 'product')}_设计方案.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_current_design_text",
        )
        prompt_text = "\n\n".join(
            f"prompt {index} · {asset.get('label', '效果图')}\n{asset.get('prompt', '')}"
            for index, asset in enumerate(current_assets, start=1)
        )
        st.download_button(
            "下载本次生成 prompt",
            data=prompt_text.encode("utf-8"),
            file_name=f"{package.get('target_product', 'product')}_prompts.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_current_prompts",
        )
        render_image_download_grid(current_image_paths, "download_center_current", current_assets)
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
