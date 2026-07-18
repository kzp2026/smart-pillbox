from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import secrets
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2.adapters.legacy import LegacyReader
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore, RepositoryArtifactStore, SupabaseArtifactStore
from v2.application.artifacts import ArchiveLimits, UnsafeArchive, extract_archive, inspect_archive
from v2.application.generation import GenerationCommand, GenerationService
from v2.application.history import HistoryService, RunDetail
from v2.application.image_generation import ImageGenerationService
from v2.application.imports import ImportService
from v2.application.migration import MigrationService
from v2.auth import LoginGuard, SessionClock
from v2.config import AppConfig, ConfigError
from v2.domain.models import ArtifactKind, CreateRunCommand
from v2.pipeline.catalog import LEGACY_STAGES
from v2.pipeline.runner import PipelineRunner, SubprocessStageExecutor
from v2.providers.images import ExistingImageProvider
from v2.providers.text import DeepSeekTextProvider
from v2.ui.components import (
    action_grid_html,
    brand_html,
    mascot_html,
    metric_grid_html,
    panel_open_html,
    process_bar_html,
    product_rows_html,
    status_bar_html,
    login_intro_html,
)
from v2.ui.errors import public_error_message
from v2.ui.theme import inject_theme


STAGE_NAV_ITEMS = (
    "导入评论资产",
    "需求生成",
    "知识库概览",
    "需求-功能-结构图谱",
    "设计方案",
    "工业设计 Prompt",
    "AI 效果图",
)
NAV_ITEMS = STAGE_NAV_ITEMS + ("历史记录", "设置与迁移")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

_LOGIN_GUARDS: dict[str, LoginGuard] = {}
_REPOSITORIES: dict[tuple[str, str, str], KnowledgeRepository] = {}
_STORES: dict[tuple[str, ...], object] = {}


def masked_service_summary(config: AppConfig) -> dict[str, str]:
    local_database = config.database_url.startswith("sqlite:///")
    return {
        "数据库": "SQLite 私有库" if local_database else "PostgreSQL 私有 schema",
        "对象存储": "本地私有目录" if local_database else (
            "Supabase 私有桶"
            if config.storage_url and config.storage_service_key
            else "PostgreSQL 私有归档"
        ),
        "DeepSeek": "已配置" if config.deepseek_api_key else "离线规则回退",
        "图像服务": "已配置" if config.image_api_key else "未配置",
        "图像模型": config.image_model,
    }


def _config_values(st_module: object) -> dict[str, object]:
    values: dict[str, object] = {
        key: value for key, value in os.environ.items() if key.startswith("V2_")
    }
    try:
        values.update(
            {
                key: value
                for key, value in dict(st_module.secrets).items()
                if str(key).startswith("V2_")
            }
        )
    except Exception:
        pass
    return values


def _guard_for(config: AppConfig) -> LoginGuard:
    key = hashlib.sha256(
        f"{config.username}\x1f{config.password_hash}".encode("utf-8")
    ).hexdigest()
    if key not in _LOGIN_GUARDS:
        _LOGIN_GUARDS[key] = LoginGuard(
            config.username,
            config.password_hash,
            config.login_max_failures,
            config.login_cooldown_seconds,
        )
    return _LOGIN_GUARDS[key]


def _repository_for(config: AppConfig) -> KnowledgeRepository:
    key = (config.database_url, config.owner_id, config.schema)
    if key not in _REPOSITORIES:
        repository = KnowledgeRepository(*key)
        repository.initialize()
        _REPOSITORIES[key] = repository
    return _REPOSITORIES[key]


def _store_for(config: AppConfig, repository: KnowledgeRepository):
    if config.database_url.startswith("sqlite:///"):
        database_path = Path(config.database_url.removeprefix("sqlite:///"))
        root = database_path.parent / f"{database_path.stem}-artifacts"
        key = ("local", str(root.resolve()))
        if key not in _STORES:
            _STORES[key] = LocalArtifactStore(root)
        return _STORES[key]
    if not config.storage_url or not config.storage_service_key:
        key = ("repository", config.database_url, config.owner_id, config.schema)
        if key not in _STORES:
            _STORES[key] = RepositoryArtifactStore(repository)
        return _STORES[key]
    key = (
        "supabase",
        config.storage_url,
        config.storage_bucket,
        hashlib.sha256(config.storage_service_key.encode("utf-8")).hexdigest(),
    )
    if key not in _STORES:
        _STORES[key] = SupabaseArtifactStore(
            config.storage_url,
            config.storage_bucket,
            config.storage_service_key,
        )
    return _STORES[key]


def _authenticated(st_module: object, config: AppConfig) -> bool:
    if not bool(st_module.session_state.get("v2_authenticated")):
        return False
    now = time.time()
    last_activity = float(st_module.session_state.get("v2_last_activity", 0))
    if SessionClock(config.session_idle_seconds).is_expired(last_activity, now):
        st_module.session_state["v2_authenticated"] = False
        st_module.session_state.pop("v2_last_activity", None)
        return False
    st_module.session_state["v2_last_activity"] = now
    return True


def _render_login(st_module: object, config: AppConfig) -> None:
    left, center, right = st_module.columns([1, 1.08, 1])
    with center:
        with st_module.container(border=True):
            st_module.markdown(login_intro_html(), unsafe_allow_html=True)
            with st_module.form("v2_login_form", clear_on_submit=True):
                username = st_module.text_input(
                    "用户名", key="login_username", autocomplete="username"
                )
                password = st_module.text_input(
                    "密码",
                    type="password",
                    key="login_password",
                    autocomplete="current-password",
                )
                submitted = st_module.form_submit_button(
                    "安全登录", icon=":material/lock:", use_container_width=True
                )
            if submitted:
                decision = _guard_for(config).authenticate(username, password, time.time())
                if decision.status == "authenticated":
                    st_module.session_state["v2_authenticated"] = True
                    st_module.session_state["v2_last_activity"] = time.time()
                    st_module.rerun()
                elif decision.status == "locked":
                    st_module.error(f"连续失败次数过多，请在 {decision.retry_after_seconds} 秒后重试。")
                else:
                    st_module.error("用户名或密码不正确。")
            st_module.caption("登录成功前不会连接业务数据库，也不会加载任何私有产品数据。")


def _logout(st_module: object) -> None:
    for key in tuple(st_module.session_state.keys()):
        if str(key).startswith("v2_") or str(key).startswith("login_"):
            del st_module.session_state[key]
    st_module.rerun()


def _sync_navigation(st_module: object, source_key: str, target_key: str) -> None:
    st_module.session_state[target_key] = st_module.session_state[source_key]


def _render_sidebar(st_module: object, config: AppConfig) -> str:
    with st_module.sidebar:
        st_module.markdown(brand_html(), unsafe_allow_html=True)
        navigation = st_module.radio(
            "工作台导航",
            NAV_ITEMS,
            index=2,
            key="v2_navigation",
            label_visibility="visible",
            on_change=_sync_navigation,
            args=(st_module, "v2_navigation", "v2_mobile_navigation"),
        )
        st_module.divider()
        summary = masked_service_summary(config)
        st_module.markdown("#### 服务状态")
        for name, state in summary.items():
            st_module.caption(f"{name} · {state}")
        st_module.divider()
        st_module.caption("私有空间 · 单用户 · 8 小时无操作自动退出")
        st_module.button(
            "退出登录",
            icon=":material/logout:",
            use_container_width=True,
            on_click=_logout,
            args=(st_module,),
        )
    return str(navigation)


def _render_mobile_navigation(st_module: object) -> str:
    if "v2_mobile_navigation" not in st_module.session_state:
        st_module.session_state["v2_mobile_navigation"] = st_module.session_state.get(
            "v2_navigation", "知识库概览"
        )
    with st_module.container(key="v2_mobile_nav"):
        navigation = st_module.selectbox(
            "移动端导航",
            NAV_ITEMS,
            index=None,
            key="v2_mobile_navigation",
            on_change=_sync_navigation,
            args=(st_module, "v2_mobile_navigation", "v2_navigation"),
        )
    if navigation is None:
        navigation = "知识库概览"
        st_module.session_state["v2_mobile_navigation"] = navigation
        st_module.session_state["v2_navigation"] = navigation
    return str(navigation)


def _service_is_healthy(repository: KnowledgeRepository) -> bool:
    try:
        repository.count_rows("products")
    except Exception:
        return False
    return True


def _completed_steps(repository: KnowledgeRepository) -> set[int]:
    completed: set[int] = set()
    try:
        if repository.count_rows("comments"):
            completed.add(0)
        if repository.count_rows("requirements"):
            completed.add(1)
        if repository.count_rows("products"):
            completed.add(2)
        if repository.count_rows("generation_runs"):
            completed.update({4, 5})
        if any(str(item.get("kind")) == ArtifactKind.IMAGE.value for item in repository.list_artifacts()):
            completed.add(6)
    except Exception:
        return completed
    return completed


def _render_header(
    st_module: object,
    config: AppConfig,
    repository: KnowledgeRepository,
    navigation: str,
) -> None:
    summary = masked_service_summary(config)
    st_module.markdown(
        status_bar_html(
            database=summary["数据库"],
            text_model=config.deepseek_model if config.deepseek_api_key else "离线规则",
            image_model=config.image_model,
            healthy=_service_is_healthy(repository),
        ),
        unsafe_allow_html=True,
    )
    if navigation in STAGE_NAV_ITEMS:
        active_index = STAGE_NAV_ITEMS.index(navigation)
        st_module.markdown(
            process_bar_html(
                active_index=active_index,
                completed_indices=_completed_steps(repository),
            ),
            unsafe_allow_html=True,
        )


def _safe_filename(name: str) -> str:
    return Path(str(name or "artifact")).name.replace("\x00", "")[:120] or "artifact"


def _artifact_kind(name: str, mime_type: str) -> ArtifactKind:
    lower = name.lower()
    if mime_type.startswith("image/"):
        return ArtifactKind.IMAGE
    if lower.endswith((".csv", ".xlsx", ".xls")):
        return ArtifactKind.TABLE
    if lower.endswith(".zip"):
        return ArtifactKind.ARCHIVE
    return ArtifactKind.DOCUMENT


def _current_detail(
    st_module: object,
    history: HistoryService,
    include_data: bool = True,
) -> RunDetail | None:
    runs = history.list_runs(50)
    if not runs:
        return None
    known_ids = {run.id for run in runs}
    selected = str(st_module.session_state.get("v2_current_run_id") or "")
    if selected not in known_ids:
        selected = runs[0].id
        st_module.session_state["v2_current_run_id"] = selected
    try:
        return history.reopen(selected, include_artifact_data=include_data)
    except Exception as exc:
        st_module.error(
            public_error_message("读取历史结果失败", exc, guidance="请刷新后重试。")
        )
        return None


def _render_overview(
    st_module: object,
    repository: KnowledgeRepository,
    history: HistoryService,
) -> None:
    products = repository.list_products()
    runs = history.list_runs(8)
    artifacts = repository.list_artifacts()
    updated = products[0].updated_at[:16].replace("T", " ") if products else "暂无数据"
    st_module.markdown(panel_open_html("知识库概览", "独立 V2 私有知识库") + metric_grid_html([
        ("产品资产", len(products), "个产品", "blue"),
        ("评论沉淀", repository.count_rows("comments"), "条评论", "cyan"),
        ("需求证据", repository.count_rows("requirements"), "条有效证据", "violet"),
        ("最近更新", updated, "数据库时间", "amber"),
    ]) + "</section>", unsafe_allow_html=True)

    left, right = st_module.columns([1.25, 0.85])
    with left:
        rows = [
            {
                "name": item.name,
                "comments": item.comment_count,
                "requirements": item.requirement_count,
                "updated_at": item.updated_at[:10],
            }
            for item in products[:8]
        ]
        st_module.markdown(
            panel_open_html("产品资产列表", f"共 {len(products)} 个产品")
            + product_rows_html(rows)
            + "</section>",
            unsafe_allow_html=True,
        )
    with right:
        st_module.markdown(
            panel_open_html("下一步动作", "常用工作入口")
            + action_grid_html(
                [
                    ("导入评论资产", "从平台导入新的评论数据", "blue"),
                    ("生成需求", "基于评论证据生成功能需求", "violet"),
                    ("数据分析", "查看关键词、情感和聚类结果", "green"),
                    ("渲染效果图", "生成并归档工业设计效果图", "amber"),
                ]
            )
            + "</section>",
            unsafe_allow_html=True,
        )

    st_module.markdown(panel_open_html("结果预览", f"{len(artifacts)} 个归档文件") + "</section>", unsafe_allow_html=True)
    if not runs:
        st_module.info("还没有运行记录。导入评论后即可开始完整分析与生成。")
    else:
        st_module.dataframe(
            [
                {
                    "产品": run.target_product,
                    "状态": run.status.value,
                    "当前阶段": run.current_stage or "—",
                    "模型": run.model,
                    "更新时间": run.updated_at[:19].replace("T", " "),
                }
                for run in runs
            ],
            hide_index=True,
            use_container_width=True,
        )

    with st_module.expander("产品管理", expanded=False):
        if not products:
            st_module.caption("暂无可管理产品。")
        else:
            selected_id = st_module.selectbox(
                "选择产品",
                [item.id for item in products],
                format_func=lambda value: next(item.name for item in products if item.id == value),
                key="v2_manage_product",
            )
            selected = next(item for item in products if item.id == selected_id)
            with st_module.form("v2_product_edit"):
                name = st_module.text_input("产品名称", selected.name)
                category = st_module.text_input("产品分类", selected.category)
                description = st_module.text_area("产品说明", selected.description)
                if st_module.form_submit_button("保存修改", icon=":material/save:"):
                    repository.update_product(selected.id, name, category, description)
                    st_module.success("产品信息已更新。")
                    st_module.rerun()
            confirm_delete = st_module.checkbox(
                f"确认删除“{selected.name}”及其评论和需求证据",
                key=f"v2_delete_confirm_{selected.id}",
            )
            if st_module.button(
                "删除产品数据",
                icon=":material/delete:",
                disabled=not confirm_delete,
                type="secondary",
            ):
                repository.delete_product(selected.id)
                st_module.success("产品及其关联评论、需求已删除。运行历史未被误删。")
                st_module.rerun()


def _create_import_run(
    repository: KnowledgeRepository,
    store: object,
    product_name: str,
    filename: str,
    file_bytes: bytes,
) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()
    run = repository.create_pipeline_run(
        CreateRunCommand(product_name, "评论资产导入与完整分析", "local", "legacy-pipeline", 0),
        idempotency_key=f"import:{product_name}:{digest}",
    )
    stored = store.put(run.id, _safe_filename(filename), file_bytes, mimetypes.guess_type(filename)[0] or "application/octet-stream")
    repository.record_artifact(run.id, ArtifactKind.INPUT, stored)
    work_dir = ROOT / "output" / "v2-work" / run.id
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / _safe_filename(filename)
    input_path.write_bytes(file_bytes)
    return run.id, str(input_path)


def _render_import(
    st_module: object,
    config: AppConfig,
    repository: KnowledgeRepository,
    store: object,
) -> None:
    st_module.markdown("### 导入评论资产")
    st_module.caption("支持 CSV、XLSX、XLS；单文件最大 50 MB。导入会去重，并自动沉淀需求证据。")
    product_name = st_module.text_input("产品名称", placeholder="例如：智能药盒")
    category = st_module.text_input("产品分类", placeholder="例如：适老健康")
    uploaded = st_module.file_uploader("上传评论文件", type=["csv", "xlsx", "xls"])
    if not uploaded:
        st_module.info("上传后会先显示表格预览和可选评论列，不会自动写入数据库。")
        return
    data = uploaded.getvalue()
    if len(data) > MAX_UPLOAD_BYTES:
        st_module.error("文件超过 50 MB，未进行解析或写入。")
        return
    try:
        from scripts.upload_parsing import candidate_comment_columns, default_comment_column, extract_comments, read_upload_table

        dataframe = read_upload_table(uploaded.name, data)
        candidates = candidate_comment_columns(dataframe)
    except Exception as exc:
        st_module.error(
            public_error_message("文件解析失败", exc, guidance="请确认文件格式正确后重试。")
        )
        return
    st_module.dataframe(dataframe.head(50), hide_index=True, use_container_width=True)
    if not candidates:
        st_module.error("没有检测到可用的文本列。请确认文件包含评论内容。")
        return
    default_column = default_comment_column(dataframe)
    comment_column = st_module.selectbox(
        "评论内容列", candidates, index=candidates.index(default_column) if default_column in candidates else 0
    )
    comments = extract_comments(dataframe, comment_column)
    st_module.caption(f"可导入 {len(comments)} 条非空评论。")
    if st_module.button("导入并沉淀知识库", icon=":material/upload:", type="primary"):
        if not product_name.strip():
            st_module.error("请先填写产品名称。")
        else:
            result = ImportService(repository).import_comments(
                product_name, category, uploaded.name, comments
            )
            run_id, input_path = _create_import_run(
                repository, store, product_name, uploaded.name, data
            )
            st_module.session_state["v2_current_run_id"] = run_id
            st_module.session_state["v2_last_input_path"] = input_path
            st_module.session_state["v2_last_product_name"] = product_name
            st_module.success(
                f"导入完成：新增 {result.report.inserted_count} 条评论，跳过 "
                f"{result.report.duplicate_count} 条重复，新增 {result.new_requirement_count} 条需求证据。"
            )

    run_id = st_module.session_state.get("v2_current_run_id")
    input_path = st_module.session_state.get("v2_last_input_path")
    last_product = st_module.session_state.get("v2_last_product_name")
    if run_id and input_path and Path(str(input_path)).exists():
        st_module.divider()
        st_module.markdown("#### 原站完整分析流水线")
        st_module.caption("保留原有清洗、关键词、情感、聚类、映射、图谱、参数、方案、效果图和评价 10 个阶段。")
        environment = {
            "DEEPSEEK_API_KEY": config.deepseek_api_key,
            "DEEPSEEK_MODEL": config.deepseek_model,
            "DEEPSEEK_BASE_URL": config.deepseek_base_url,
            "IMAGE_PROVIDER": config.image_provider,
            "IMAGE_MODEL": config.image_model,
        }
        if config.image_provider.lower() == "dashscope":
            environment["DASHSCOPE_API_KEY"] = config.image_api_key
        else:
            environment["IMAGE_API_KEY"] = config.image_api_key
            environment["IMAGE_BASE_URL"] = config.image_base_url
        runner = PipelineRunner(
            repository,
            store,
            SubprocessStageExecutor(
                ROOT,
                ROOT / "output" / "v2-runs",
                environment=environment,
            ),
        )
        selected_stage = st_module.selectbox(
            "选择单独运行的原站阶段",
            LEGACY_STAGES,
            format_func=lambda stage: f"{stage.id} · {stage.label}",
            help="适合重跑某一步；依赖前序结果的阶段应在对应结果已存在时运行。",
        )
        run_all_column, run_stage_column = st_module.columns(2)
        if run_all_column.button("运行全部 10 个阶段", icon=":material/play_arrow:"):
            with st_module.spinner("正在运行完整流水线，请勿关闭页面……"):
                result = runner.run_all(str(run_id), str(last_product), str(input_path))
            if result.failed_stage_id:
                st_module.warning(
                    f"已保留前 {len(result.completed_stage_ids)} 个成功阶段；阶段 {result.failed_stage_id} 失败。"
                )
            else:
                st_module.success("完整流水线运行成功，所有结果已写入私有归档。")
        if run_stage_column.button("运行选中阶段", icon=":material/step_into:"):
            with st_module.spinner(f"正在运行阶段 {selected_stage.id} · {selected_stage.label}……"):
                result = runner.run_stage(
                    str(run_id), selected_stage.id, str(last_product), str(input_path)
                )
            if result.failed_stage_id:
                st_module.warning(
                    f"阶段 {selected_stage.id} 运行失败；已有历史结果未被覆盖，请检查前序依赖或服务配置。"
                )
            else:
                st_module.success(
                    f"阶段 {selected_stage.id} · {selected_stage.label} 已完成并写入私有归档。"
                )


def _constraint_inputs(st_module: object) -> dict[str, str]:
    first, second = st_module.columns(2)
    with first:
        product_type = st_module.text_input("产品类型", placeholder="桌面智能硬件")
        target_users = st_module.text_input("目标用户", placeholder="老年用户及家庭照护者")
        core_functions = st_module.text_area("核心功能", placeholder="定时提醒、分格收纳、状态反馈")
        structure = st_module.text_area("结构锁定", placeholder="透明翻盖、独立分格、前置交互区")
    with second:
        materials = st_module.text_input("材料与工艺", placeholder="食品级 ABS、透明 PC、硅胶密封")
        colors = st_module.text_input("颜色与 CMF", placeholder="暖白主体、低饱和蓝色强调")
        dimensions = st_module.text_input("尺寸与比例", placeholder="紧凑桌面尺寸，适合单手操作")
        forbidden = st_module.text_area("禁止修改项", placeholder="不得改变核心分格数量和主要交互位置")
    return {
        "product_type": product_type,
        "target_users": target_users,
        "core_functions": core_functions,
        "structure": structure,
        "materials": materials,
        "colors": colors,
        "dimensions": dimensions,
        "forbidden_changes": forbidden,
    }


def _image_provider_config(config: AppConfig) -> dict[str, object]:
    provider = config.image_provider.strip().lower() or "dashscope"
    if provider == "dashscope":
        return {
            "provider": "dashscope",
            "api_key": config.image_api_key,
            "model": config.image_model,
            "base_url": config.image_base_url or "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
            "multimodal_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            "task_url": "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
            "quality": "standard",
            "prompt_extend": False,
        }
    return {
        "provider": "openai",
        "api_key": config.image_api_key,
        "model": config.image_model,
        "base_url": config.image_base_url or None,
        "quality": "medium",
    }


def _generation_services(config: AppConfig, repository: KnowledgeRepository):
    confirmation_secret = hashlib.sha256(config.password_hash.encode("utf-8")).digest()
    return (
        GenerationService(repository, confirmation_secret),
        DeepSeekTextProvider(
            config.deepseek_api_key,
            config.deepseek_model,
            config.deepseek_base_url,
        ),
    )


def _render_demand(
    st_module: object,
    config: AppConfig,
    repository: KnowledgeRepository,
    store: object,
) -> None:
    st_module.markdown("### 需求生成与设计任务")
    products = repository.list_products()
    options = [item.name for item in products]
    default_product = options[0] if options else ""
    target_product = st_module.text_input("目标产品", value=default_product)
    demand_text = st_module.text_area(
        "本次设计需求",
        placeholder="例如：强化提醒感知与防潮能力，同时保持适老化易用性。",
        height=110,
    )
    with st_module.expander("工业设计约束", expanded=True):
        constraints = _constraint_inputs(st_module)
    model_col, count_col = st_module.columns(2)
    with model_col:
        provider = st_module.selectbox(
            "图片供应商", [config.image_provider], disabled=True
        )
        model = st_module.text_input("图片模型", value=config.image_model, disabled=True)
    with count_col:
        image_count = st_module.number_input(
            "效果图数量", min_value=0, max_value=8, value=8, step=1
        )
        st_module.caption("0 张仅生成设计方案和 Prompt，不调用付费图片接口。")

    if st_module.button("生成任务预览", icon=":material/preview:", type="primary"):
        if not target_product.strip() or not demand_text.strip():
            st_module.error("目标产品和本次设计需求不能为空。")
        elif int(image_count) > 0 and not config.image_api_key:
            st_module.error("尚未配置图像服务密钥。可将效果图数量设为 0，先生成完整文字方案。")
        else:
            command = GenerationCommand(
                target_product.strip(),
                demand_text.strip(),
                str(provider),
                str(model),
                int(image_count),
            )
            service, _ = _generation_services(config, repository)
            preview = service.preview(command, secrets.token_urlsafe(18))
            st_module.session_state["v2_generation_preview"] = preview
            st_module.session_state["v2_generation_command"] = command
            st_module.session_state["v2_generation_constraints"] = constraints

    preview = st_module.session_state.get("v2_generation_preview")
    command = st_module.session_state.get("v2_generation_command")
    if preview and command:
        st_module.info(
            f"即将使用 {preview.provider} / {preview.model}；计划生成 {preview.image_count} 张效果图。"
        )
        confirmed = st_module.checkbox(
            "我已核对供应商、模型和图片数量，并确认可能产生对应费用。",
            value=preview.image_count == 0,
            disabled=preview.image_count == 0,
        )
        if st_module.button(
            "确认并开始生成",
            icon=":material/auto_awesome:",
            disabled=not confirmed,
        ):
            service, text_provider = _generation_services(config, repository)
            provided_token = preview.confirmation_token if confirmed else None
            run = service.confirm_and_start(command, preview, provided_token)
            with st_module.spinner("正在检索私有证据并生成设计方案……"):
                generated = service.generate_design(
                    run.id,
                    command,
                    st_module.session_state.get("v2_generation_constraints", {}),
                    text_provider,
                )
            if command.image_count:
                provider_client = ExistingImageProvider(_image_provider_config(config))
                with st_module.spinner(f"正在生成 {command.image_count} 张效果图……"):
                    report = ImageGenerationService(repository, store, provider_client).generate(
                        run.id,
                        list(generated.package.get("visual_assets") or []),
                        command.image_count,
                    )
                if report.failures:
                    st_module.warning(
                        f"已成功保存 {report.succeeded_count}/{report.requested_count} 张；失败项已保留诊断。"
                    )
                else:
                    st_module.success(f"已生成并归档 {report.succeeded_count} 张效果图。")
            else:
                st_module.success("设计方案与工业设计 Prompt 已生成。")
            st_module.session_state["v2_current_run_id"] = run.id
            st_module.session_state.pop("v2_generation_preview", None)
            st_module.session_state.pop("v2_generation_command", None)


def _render_artifact(st_module: object, artifact: object) -> None:
    data = artifact.data or b""
    name = artifact.name
    mime_type = artifact.mime_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    if mime_type.startswith("image/"):
        st_module.image(data, caption=name, use_container_width=True)
    elif name.lower().endswith(".csv"):
        try:
            import pandas as pd

            st_module.dataframe(pd.read_csv(io.BytesIO(data)), hide_index=True, use_container_width=True)
        except Exception as exc:
            st_module.warning(
                public_error_message("CSV 预览失败", exc, guidance="仍可下载原文件。")
            )
    elif name.lower().endswith((".xlsx", ".xls")):
        try:
            import pandas as pd

            workbook = pd.ExcelFile(io.BytesIO(data))
            sheet = st_module.selectbox(
                "工作表", workbook.sheet_names, key=f"v2_sheet_{artifact.id}"
            )
            st_module.dataframe(
                pd.read_excel(workbook, sheet_name=sheet), hide_index=True, use_container_width=True
            )
        except Exception as exc:
            st_module.warning(
                public_error_message("表格预览失败", exc, guidance="仍可下载原文件。")
            )
    elif name.lower().endswith((".txt", ".md", ".json", ".cypher")):
        st_module.code(data.decode("utf-8", errors="replace"), language="json" if name.endswith(".json") else None)
    st_module.download_button(
        f"下载 {name}", data=data, file_name=name, mime=mime_type, icon=":material/download:"
    )


def _render_graph(st_module: object, history: HistoryService) -> None:
    st_module.markdown("### 需求—功能—结构图谱")
    detail = _current_detail(st_module, history, include_data=True)
    if not detail:
        st_module.info("暂无结果。请先运行完整流水线。")
        return
    candidates = [
        item
        for item in detail.artifacts
        if item.name.lower().endswith((".csv", ".xlsx", ".xls", ".json", ".cypher"))
    ]
    if not candidates:
        st_module.info("当前运行尚未生成可视化图谱或映射表。已完成的其他结果仍安全保留。")
        return
    selected = st_module.selectbox(
        "选择映射或图谱文件",
        candidates,
        format_func=lambda item: item.name,
    )
    _render_artifact(st_module, selected)


def _render_design(st_module: object, history: HistoryService) -> None:
    st_module.markdown("### 设计方案")
    detail = _current_detail(st_module, history, include_data=True)
    if not detail:
        st_module.info("暂无设计方案。请先在“需求生成”中创建任务。")
        return
    if detail.quality_status:
        score = f"{detail.quality_score:.1f}" if detail.quality_score else "—"
        st_module.caption(f"质量状态：{detail.quality_status} · 评分：{score}")
    design_text = str(detail.result.get("design_text") or "")
    if design_text:
        st_module.markdown(design_text)
        st_module.download_button(
            "下载 Markdown 方案",
            design_text.encode("utf-8"),
            file_name=f"{_safe_filename(detail.run.target_product)}-设计方案.md",
            mime="text/markdown",
            icon=":material/download:",
        )
    else:
        st_module.info("该运行暂无结构化方案文本，可在下方下载原站归档文件。")
    documents = [item for item in detail.artifacts if item.kind == ArtifactKind.DOCUMENT.value]
    for artifact in documents:
        _render_artifact(st_module, artifact)


def _render_prompt(st_module: object, history: HistoryService) -> None:
    st_module.markdown("### 工业设计 Prompt")
    detail = _current_detail(st_module, history, include_data=False)
    if not detail:
        st_module.info("暂无 Prompt。请先生成设计方案。")
        return
    prompt = str(detail.result.get("industrial_design_prompt") or "")
    if prompt:
        st_module.code(prompt, language=None, wrap_lines=True)
    prompts = list(detail.result.get("image_prompts") or [])
    if not prompts:
        st_module.info("该历史记录没有结构化图片 Prompt。")
        return
    for index, item in enumerate(prompts, start=1):
        with st_module.expander(f"图像任务 {index}", expanded=index == 1):
            st_module.code(str(item), language=None, wrap_lines=True)


def _render_images(
    st_module: object,
    config: AppConfig,
    repository: KnowledgeRepository,
    store: object,
    history: HistoryService,
) -> None:
    st_module.markdown("### AI 效果图")
    detail = _current_detail(st_module, history, include_data=True)
    if not detail:
        st_module.info("暂无效果图。请先创建生成任务。")
        return
    images = [item for item in detail.artifacts if item.mime_type.startswith("image/")]
    if images:
        columns = st_module.columns(min(4, len(images)))
        for index, artifact in enumerate(images):
            with columns[index % len(columns)]:
                st_module.image(artifact.data or b"", caption=artifact.name, use_container_width=True)
                st_module.download_button(
                    "下载原图",
                    data=artifact.data or b"",
                    file_name=artifact.name,
                    mime=artifact.mime_type,
                    key=f"v2_download_image_{artifact.id}",
                    icon=":material/download:",
                    use_container_width=True,
                )
    else:
        st_module.info("该任务尚无图片文件；设计方案和 Prompt 仍可正常使用。")

    st_module.divider()
    st_module.markdown("#### 重新生成")
    if not config.image_api_key:
        st_module.caption("配置图像服务后，可基于同一证据与结构约束重新生成。")
        return
    count = st_module.number_input(
        "重新生成数量", min_value=1, max_value=8, value=min(8, max(1, detail.run.image_count or 8)), key="v2_regen_count"
    )
    confirmed = st_module.checkbox(
        f"确认使用 {config.image_provider} / {config.image_model} 重新生成 {int(count)} 张，并可能产生费用。",
        key="v2_regen_confirm",
    )
    if st_module.button(
        "确认并重新生成",
        icon=":material/refresh:",
        disabled=not confirmed,
    ):
        command = GenerationCommand(
            detail.run.target_product,
            detail.run.demand_text,
            config.image_provider,
            config.image_model,
            int(count),
        )
        service, text_provider = _generation_services(config, repository)
        preview = service.preview(command, secrets.token_urlsafe(18))
        run = service.confirm_and_start(command, preview, preview.confirmation_token)
        constraints = detail.context.get("industrial_constraints") or {}
        generated = service.generate_design(run.id, command, constraints, text_provider)
        report = ImageGenerationService(
            repository, store, ExistingImageProvider(_image_provider_config(config))
        ).generate(run.id, list(generated.package.get("visual_assets") or []), int(count))
        st_module.session_state["v2_current_run_id"] = run.id
        if report.failures:
            st_module.warning(f"重新生成完成：成功 {report.succeeded_count}/{report.requested_count} 张。")
        else:
            st_module.success("重新生成完成，已创建新的可追溯运行记录。")
        st_module.rerun()


def _zip_run(detail: RunDetail) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if detail.result:
            archive.writestr(
                "generation-result.json",
                json.dumps(detail.result, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        for artifact in detail.artifacts:
            if artifact.data is not None:
                archive.writestr(_safe_filename(artifact.name), artifact.data)
    return output.getvalue()


def _render_history(
    st_module: object,
    repository: KnowledgeRepository,
    store: object,
    history: HistoryService,
) -> None:
    st_module.markdown("### 历史记录")
    runs = history.list_runs(100)
    if not runs:
        st_module.info("暂无历史记录。")
    else:
        options = {run.id: run for run in runs}
        selected_id = st_module.selectbox(
            "选择运行记录",
            list(options),
            index=list(options).index(st_module.session_state.get("v2_current_run_id"))
            if st_module.session_state.get("v2_current_run_id") in options
            else 0,
            format_func=lambda run_id: (
                f"{options[run_id].target_product} · {options[run_id].status.value} · "
                f"{options[run_id].updated_at[:19].replace('T', ' ')}"
            ),
        )
        st_module.session_state["v2_current_run_id"] = selected_id
        detail = history.reopen(selected_id, include_artifact_data=True)
        first, second, third, fourth = st_module.columns(4)
        first.metric("状态", detail.run.status.value)
        second.metric("图片计划", detail.run.image_count)
        third.metric("归档文件", len(detail.artifacts))
        fourth.metric("质量分", f"{detail.quality_score:.1f}" if detail.quality_score else "—")
        archive_data = _zip_run(detail)
        st_module.download_button(
            "批量下载本次全部结果",
            archive_data,
            file_name=f"{_safe_filename(detail.run.target_product)}-{detail.run.id[:8]}.zip",
            mime="application/zip",
            icon=":material/archive:",
        )
        if detail.result.get("design_text"):
            with st_module.expander("设计方案预览", expanded=True):
                st_module.markdown(str(detail.result["design_text"]))
        for artifact in detail.artifacts:
            with st_module.expander(f"{artifact.name} · {artifact.size_bytes / 1024:.1f} KB"):
                _render_artifact(st_module, artifact)

    st_module.divider()
    st_module.markdown("#### 恢复结果归档")
    archive_upload = st_module.file_uploader(
        "上传 ZIP 归档",
        type=["zip"],
        key="v2_archive_restore",
        help="会先检查路径、条目数、展开大小、压缩比和文件类型。",
    )
    if archive_upload:
        archive_bytes = archive_upload.getvalue()
        try:
            manifest = inspect_archive(archive_bytes, ArchiveLimits.default())
            st_module.success(
                f"安全检查通过：{len(manifest.entries)} 个文件，展开后 {manifest.total_uncompressed / 1024 / 1024:.1f} MB。"
            )
        except UnsafeArchive as exc:
            st_module.error(str(exc))
            return
        if st_module.button("归档为新的历史记录", icon=":material/unarchive:"):
            digest = hashlib.sha256(archive_bytes).hexdigest()
            run = repository.create_pipeline_run(
                CreateRunCommand("恢复的历史结果", "安全 ZIP 归档恢复", "archive", "restored", 0),
                idempotency_key=f"restore:{digest}",
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                target = Path(temp_dir)
                extract_archive(archive_bytes, target, ArchiveLimits.default())
                for path in target.rglob("*"):
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                    name = _safe_filename(path.name)
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    stored = store.put(run.id, name, data, mime)
                    repository.record_artifact(run.id, _artifact_kind(name, mime), stored)
            st_module.session_state["v2_current_run_id"] = run.id
            st_module.success("归档已恢复到独立 V2 历史记录。")


def _migration_service(
    config: AppConfig,
    repository: KnowledgeRepository,
    store: object,
) -> MigrationService:
    roots = [
        (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value)
        for value in config.legacy_output_roots
    ]
    return MigrationService(
        LegacyReader(config.legacy_database_url, owner_id="private", output_roots=roots),
        repository,
        store,
    )


def _render_settings(
    st_module: object,
    config: AppConfig,
    repository: KnowledgeRepository,
    store: object,
) -> None:
    st_module.markdown("### 设置与迁移")
    st_module.markdown("#### 服务配置（已脱敏）")
    st_module.table(
        [{"服务": name, "状态": value} for name, value in masked_service_summary(config).items()]
    )
    if st_module.button("检查数据库连接", icon=":material/database:"):
        try:
            counts = {
                name: repository.count_rows(name)
                for name in ("products", "comments", "requirements", "pipeline_runs", "artifacts")
            }
            st_module.success(f"连接正常：{counts}")
        except Exception as exc:
            st_module.error(public_error_message("连接检查失败", exc))

    st_module.divider()
    st_module.markdown("#### 原站数据复制")
    st_module.caption("迁移采用先预演、再复制、最后校验；不会修改或删除原站数据。可重复执行且不会重复导入。")
    if not config.legacy_database_url and not config.legacy_output_roots:
        st_module.info("尚未配置 V2_LEGACY_DATABASE_URL / V2_LEGACY_OUTPUT_ROOTS。原站保持不变。")
        return
    service = _migration_service(config, repository, store)
    first, second, third = st_module.columns(3)
    if first.button("1. 迁移预演", icon=":material/fact_check:"):
        try:
            report = service.dry_run()
            st_module.session_state["v2_migration_report"] = report
        except Exception as exc:
            st_module.error(public_error_message("预演失败", exc))
    apply_confirmed = st_module.checkbox("确认仅复制数据，不更改原站", key="v2_migration_confirm")
    if second.button("2. 开始复制", icon=":material/content_copy:", disabled=not apply_confirmed):
        try:
            report = service.apply()
            st_module.session_state["v2_migration_report"] = report
            st_module.success(f"复制完成：新增 {report.migrated_total} 项，跳过 {report.skipped_total} 项。")
        except Exception as exc:
            st_module.error(public_error_message("复制失败", exc))
    if third.button("3. 哈希校验", icon=":material/verified:"):
        try:
            verification = service.verify()
            if verification.consistent:
                st_module.success(f"校验通过，已核验 {verification.checked_files} 个原站文件。")
            else:
                st_module.error("校验未通过：" + "；".join(verification.failed_checks))
        except Exception as exc:
            st_module.error(public_error_message("校验失败", exc))
    report = st_module.session_state.get("v2_migration_report")
    if report:
        st_module.json(
            {
                "模式": report.mode,
                "源数据": report.source_counts,
                "V2 当前数据": report.target_counts,
                "新增": report.migrated,
                "跳过": report.skipped,
            }
        )


def main() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="产品评论知识库智能体 V2",
        page_icon="AI",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme(st)
    try:
        config = AppConfig.from_mapping(_config_values(st))
    except ConfigError as exc:
        st.error(f"V2 尚未完成服务端配置：{exc}")
        st.code(
            "V2_USERNAME = \"owner\"\n"
            "V2_PASSWORD_HASH = \"scrypt$...\"\n"
            "V2_DATABASE_URL = \"postgresql://...\"",
            language="toml",
        )
        st.caption("请在新 Streamlit 应用的 Secrets 中配置。原站不受影响。")
        return

    if not _authenticated(st, config):
        _render_login(st, config)
        return

    st.session_state["login_username"] = ""
    st.session_state["login_password"] = ""

    try:
        repository = _repository_for(config)
        store = _store_for(config, repository)
    except Exception as exc:
        st.error(public_error_message("私有服务初始化失败", exc))
        st.caption("未自动回退到公共数据库或公共存储。")
        return

    history = HistoryService(repository, store)
    navigation = _render_sidebar(st, config)
    navigation = _render_mobile_navigation(st)
    _render_header(st, config, repository, navigation)
    st.markdown(mascot_html(), unsafe_allow_html=True)

    if navigation == "导入评论资产":
        _render_import(st, config, repository, store)
    elif navigation == "需求生成":
        _render_demand(st, config, repository, store)
    elif navigation == "知识库概览":
        _render_overview(st, repository, history)
    elif navigation == "需求-功能-结构图谱":
        _render_graph(st, history)
    elif navigation == "设计方案":
        _render_design(st, history)
    elif navigation == "工业设计 Prompt":
        _render_prompt(st, history)
    elif navigation == "AI 效果图":
        _render_images(st, config, repository, store, history)
    elif navigation == "历史记录":
        _render_history(st, repository, store, history)
    else:
        _render_settings(st, config, repository, store)


if __name__ == "__main__":
    main()
