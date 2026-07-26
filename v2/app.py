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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2.adapters.legacy import LegacyReader
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore, RepositoryArtifactStore, SupabaseArtifactStore
from v2.application.artifacts import ArchiveLimits, UnsafeArchive, extract_archive, inspect_archive
from v2.application.generation import GenerationCommand, GenerationService
from v2.application.generation_jobs import GenerationJobRegistry
from v2.application.history import HistoryService, RunDetail
from v2.application.image_generation import ImageGenerationService
from v2.application.image_jobs import ImageJobRegistry
from v2.application.imports import ImportService
from v2.application.migration import MigrationService
from v2.application import runtime_state as _runtime_state
from v2.application.runtime_state import (
    LOGIN_GUARDS as _LOGIN_GUARDS,
    REPOSITORIES as _REPOSITORIES,
    STORES as _STORES,
    VIEW_CACHE as _VIEW_CACHE,
)
from v2.auth import LoginGuard, SessionClock
from v2.config import AppConfig, ConfigError
from v2.domain.models import ArtifactKind, CreateRunCommand, RunStatus
from v2.pipeline.catalog import LEGACY_STAGES
from v2.pipeline.runner import PipelineRunner, SubprocessStageExecutor
from v2.providers.images import ExistingImageProvider
from v2.providers.text import DeepSeekTextProvider
from v2.ui.components import (
    brand_html,
    current_product_context_html,
    metric_grid_html,
    panel_open_html,
    process_bar_html,
    product_rows_html,
    status_bar_html,
    login_intro_html,
)
from v2.ui.errors import public_error_message
from v2.ui.theme import inject_theme


_IMAGE_JOB_REGISTRY = getattr(_runtime_state, "IMAGE_JOB_REGISTRY", None)
if _IMAGE_JOB_REGISTRY is None:
    _IMAGE_JOB_REGISTRY = ImageJobRegistry()
    setattr(_runtime_state, "IMAGE_JOB_REGISTRY", _IMAGE_JOB_REGISTRY)

_GENERATION_JOB_REGISTRY = getattr(_runtime_state, "GENERATION_JOB_REGISTRY", None)
if _GENERATION_JOB_REGISTRY is None:
    _GENERATION_JOB_REGISTRY = GenerationJobRegistry()
    setattr(_runtime_state, "GENERATION_JOB_REGISTRY", _GENERATION_JOB_REGISTRY)


STAGE_NAV_ITEMS = (
    "å¯¼å…¥è¯„è®ºèµ„äº§",
    "éœ€æ±‚ç”Ÿæˆ",
    "çŸ¥è¯†åº“æ¦‚è§ˆ",
    "éœ€æ±‚-åŠŸèƒ½-ç»“æ„å›¾è°±",
    "è®¾è®¡æ–¹æ¡ˆ",
    "å·¥ä¸šè®¾è®¡ Prompt",
    "AI æ•ˆæœå›¾",
)
NAV_ITEMS = STAGE_NAV_ITEMS + ("å†å²è®°å½•", "è®¾ç½®ä¸è¿ç§»")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEMAND_DRAFT_KEY = "v2_demand_draft"
DEMAND_WIDGET_PREFIX = "_v2_demand_"

@dataclass(frozen=True)
class _WorkspaceView:
    """Structural fallback that survives mixed-module Streamlit hot reloads."""

    product_count: int = 0
    comment_count: int = 0
    requirement_count: int = 0
    generation_run_count: int = 0
    artifact_count: int = 0
    image_count: int = 0
    healthy: bool = True


def masked_service_summary(config: AppConfig) -> dict[str, str]:
    local_database = config.database_url.startswith("sqlite:///")
    return {
        "æ•°æ®åº“": "SQLite ç§æœ‰åº“" if local_database else "PostgreSQL ç§æœ‰ schema",
        "å¯¹è±¡å­˜å‚¨": "æœ¬åœ°ç§æœ‰ç›®å½•" if local_database else (
            "Supabase ç§æœ‰æ¡¶"
            if config.storage_url and config.storage_service_key
            else "PostgreSQL ç§æœ‰å½’æ¡£"
        ),
        "DeepSeek": "å·²é…ç½®" if config.deepseek_api_key else "ç¦»çº¿è§„åˆ™å›é€€",
        "å›¾åƒæœåŠ¡": "å·²é…ç½®" if config.image_api_key else "æœªé…ç½®",
        "å›¾åƒæ¨¡å‹": config.image_model,
    }


def secret_configuration_template(config: AppConfig) -> str:
    """Build a copyable template without ever rendering current secret values."""
    model = config.image_model.strip() or "wan2.7-image-pro"
    return (
        '# åœ¨ Streamlit Cloudï¼šç®¡ç†åº”ç”¨ â†’ Settings â†’ Secrets\n'
        'V2_IMAGE_PROVIDER = "dashscope"\n'
        f"V2_IMAGE_MODEL = {json.dumps(model, ensure_ascii=False)}\n"
        'V2_IMAGE_API_KEY = "<å¡«å†™é˜¿é‡Œäº‘ç™¾ç‚¼ DashScope API Key>"'
    )


def _repository_scope(repository: KnowledgeRepository) -> str:
    return hashlib.sha256(
        f"{repository.database_url}\x1f{repository.owner_id}\x1f{repository.schema}".encode("utf-8")
    ).hexdigest()


def _cached_view(
    repository: KnowledgeRepository,
    category: str,
    loader: Callable[[], Any],
    *parts: object,
) -> Any:
    return _VIEW_CACHE.get((_repository_scope(repository), category, *parts), loader)


def _invalidate_view_cache(repository: KnowledgeRepository | None = None) -> None:
    if repository is None:
        _VIEW_CACHE.invalidate()
    else:
        _VIEW_CACHE.invalidate((_repository_scope(repository),))


def _workspace_snapshot(
    repository: KnowledgeRepository,
    target_product: str | None = None,
) -> Any:
    product = str(target_product or "").strip()

    def load() -> Any:
        try:
            if product:
                return repository.product_workspace_snapshot(product)
            return repository.workspace_snapshot()
        except Exception:
            return _WorkspaceView(healthy=False)

    return _cached_view(repository, "workspace-snapshot", load, product)


def _cached_products(repository: KnowledgeRepository):
    return _cached_view(repository, "products", repository.list_products)


def _cached_runs(
    history: HistoryService,
    limit: int,
    target_product: str | None = None,
):
    product = str(target_product or "").strip()

    requested_limit = max(1, int(limit))
    cache_limit = 100 if product else requested_limit

    def load_runs():
        if not product:
            return history.list_runs(cache_limit)
        try:
            return history.list_runs(cache_limit, target_product=product)
        except TypeError:
            return [run for run in history.list_runs(200) if run.target_product == product][:cache_limit]

    cached = _cached_view(
        history.repository,
        "pipeline-runs",
        load_runs,
        product,
        cache_limit,
    )
    return list(cached)[:requested_limit]


def _cached_run_detail(
    history: HistoryService,
    run_id: str,
    include_data: bool,
    data_mime_prefixes: tuple[str, ...] = (),
):
    prefixes = tuple(data_mime_prefixes)

    def load_detail():
        if prefixes:
            try:
                return history.reopen(
                    run_id,
                    include_artifact_data=include_data,
                    data_mime_prefixes=prefixes,
                )
            except TypeError:
                # Compatibility with a HistoryService cached from the previous deploy.
                return history.reopen(run_id, include_artifact_data=include_data)
        return history.reopen(run_id, include_artifact_data=include_data)

    return _cached_view(
        history.repository,
        "run-detail",
        load_detail,
        run_id,
        bool(include_data),
        prefixes,
    )


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
                    "ç”¨æˆ·å", key="login_username", autocomplete="username"
                )
                password = st_module.text_input(
                    "å¯†ç ",
                    type="password",
                    key="login_password",
                    autocomplete="current-password",
                )
                submitted = st_module.form_submit_button(
                    "å®‰å…¨ç™»å½•", icon=":material/lock:", use_container_width=True
                )
            if submitted:
                decision = _guard_for(config).authenticate(username, password, time.time())
                if decision.status == "authenticated":
                    st_module.session_state["v2_authenticated"] = True
                    st_module.session_state["v2_last_activity"] = time.time()
                    st_module.rerun()
                elif decision.status == "locked":
                    st_module.error(f"è¿ç»­å¤±è´¥æ¬¡æ•°è¿‡å¤šï¼Œè¯·åœ¨ {decision.retry_after_seconds} ç§’åé‡è¯•ã€‚")
                else:
                    st_module.error("ç”¨æˆ·åæˆ–å¯†ç ä¸æ­£ç¡®ã€‚")
            st_module.caption("ç™»å½•æˆåŠŸå‰ä¸ä¼šè¿æ¥ä¸šåŠ¡æ•°æ®åº“ï¼Œä¹Ÿä¸ä¼šåŠ è½½ä»»ä½•ç§æœ‰äº§å“æ•°æ®ã€‚")


def _logout(st_module: object) -> None:
    _invalidate_view_cache()
    for key in tuple(st_module.session_state.keys()):
        if str(key).startswith("v2_") or str(key).startswith("login_"):
            del st_module.session_state[key]
    st_module.rerun()


def _sync_navigation(st_module: object, source_key: str, target_key: str) -> None:
    navigation = st_module.session_state[source_key]
    st_module.session_state[target_key] = navigation
    # Large image bytes are deliberately opt-in.  Leaving the image page must
    # clear the preview flag so returning through navigation never reloads all
    # images and blocks the next page render.
    if navigation != "AI æ•ˆæœå›¾":
        st_module.session_state.pop("v2_loaded_image_run_id", None)


def _open_key_settings(st_module: object) -> None:
    target = "è®¾ç½®ä¸è¿ç§»"
    st_module.session_state["v2_navigation"] = target
    st_module.session_state["v2_mobile_navigation"] = target


def _render_sidebar(st_module: object, config: AppConfig) -> str:
    with st_module.sidebar:
        st_module.markdown(brand_html(), unsafe_allow_html=True)
        navigation = st_module.radio(
            "å·¥ä½œå°å¯¼èˆª",
            NAV_ITEMS,
            index=None if "v2_navigation" in st_module.session_state else 2,
            key="v2_navigation",
            label_visibility="visible",
            on_change=_sync_navigation,
            args=(st_module, "v2_navigation", "v2_mobile_navigation"),
        )
        st_module.divider()
        summary = masked_service_summary(config)
        st_module.markdown("#### æœåŠ¡çŠ¶æ€")
        for name, state in summary.items():
            st_module.caption(f"{name} Â· {state}")
        st_module.caption("DeepSeek å·²ç‹¬ç«‹é…ç½®ï¼›è¿™é‡Œåªå¤„ç†é˜¿é‡Œäº‘ç™¾ç‚¼æ•ˆæœå›¾ Keyã€‚")
        st_module.button(
            "é…ç½®ç™¾ç‚¼æ•ˆæœå›¾ Key",
            icon=":material/key:",
            type="primary" if not config.image_api_key else "secondary",
            use_container_width=True,
            on_click=_open_key_settings,
            args=(st_module,),
        )
        st_module.divider()
        st_module.caption("ç§æœ‰ç©ºé—´ Â· å•ç”¨æˆ· Â· 8 å°æ—¶æ— æ“ä½œè‡ªåŠ¨é€€å‡º")
        st_module.button(
            "é€€å‡ºç™»å½•",
            icon=":material/logout:",
            use_container_width=True,
            on_click=_logout,
            args=(st_module,),
        )
    return str(navigation)


def _render_mobile_navigation(st_module: object) -> str:
    if "v2_mobile_navigation" not in st_module.session_state:
        st_module.session_state["v2_mobile_navigation"] = st_module.session_state.get(
            "v2_navigation", "çŸ¥è¯†åº“æ¦‚è§ˆ"
        )
    with st_module.container(key="v2_mobile_nav"):
        navigation = st_module.selectbox(
            "ç§»åŠ¨ç«¯å¯¼èˆª",
            NAV_ITEMS,
            index=None,
            key="v2_mobile_navigation",
            on_change=_sync_navi×Í8òÚ$z{-®éÜj×Æ—7B†FV6—6–öåöÆ&VÇ2’ÀĞ¢–æFWƒÖÆ—7B†FV6—6–öåöÆ&VÇ2’æ–æFW‚†7W'&VçE÷&Wf–WræFV6—6–öâĞ¢–b7W'&VçE÷&Wf–WræFV6—6–öâ–âFV6—6–öåöÆ&VÇ0Ğ¢VÇ6RÀĞ¢f÷&ÖEögVæ3ÖFV6—6–öåöÆ&VÇ2ævWBÀĞ¢Ğ¢&F–ærÒ7EöÖöGVÆRç6Æ–FW"‚.{¹>iéÎŠøNXˆb"ÂÂRÂ–çB†7W'&VçE÷&Wf–Wrç&F–ær’Ğ¢æ÷FW2Ò7EöÖöGVÆRçFW‡Eö&V‚.ŠøNZêZH~k:‚"Â7W'&VçE÷&Wf–Wrææ÷FW2Â†V–v‡CÓ“Ğ¢—5öf–æÂÒ7EöÖöGVÆRæ6†V6¶&÷‚‚.j~ŠëK‹®iÈ{¸x˜iÊÂ"ÂfÇVSÖ7W'&VçE÷&Wf–Wræ—5öf–æÂĞ¢–b7EöÖöGVÆRæf÷&Õ÷7V&Ö—Eö'WGFöâ‚.KùŞZÙ{¹>iéÎXk>zÙb"ÂG—SÒ'&–Ö'’"“ Ğ¢†—7F÷'’ç6fU÷&Wf–Wr‡6VÆV7FVEö–BÂFV6—6–öâÂ&F–ærÂæ÷FW2Â—5öf–æÂĞ¢7EöÖöGVÆRç7V66W72‚.ŠøNZê{¹>Šë®[{.KùŞZÙ8""Ğ Ğ¢ÆöFVEöFWF–Åö–BÒ7G"‡7EöÖöGVÆRç6W76–öå÷7FFRævWB‚'c%öÆöFVEö†—7F÷'•÷'Våö–B"’÷"""Ğ¢–bÆöFVEöFWF–Åö–BÒ6VÆV7FVEö–C Ğ¢–b7EöÖöGVÆRæ'WGFöâ‚.Xª‹ÛŞih~K»nš(NŠxKˆîh›˜xşKˆ¾‹ÛÒ"Â–6öãÒ#¦ÖFW&–ÂöföÆFW%ö÷Vã¢"“ Ğ¢7EöÖöGVÆRç6W76–öå÷7FFU²'c%öÆöFVEö†—7F÷'•÷'Våö–B%ÒÒ6VÆV7FVEö–@Ğ¢7EöÖöGVÆRç&W'Vâ‚Ğ¢VÇ6S Ğ¢FWF–ÂÒö66†VE÷'VåöFWF–Â††—7F÷'’Â6VÆV7FVEö–BÂG'VRĞ¢&6†—fUöFFÒ÷¦—÷'Vâ†FWF–ÂĞ¢7EöÖöGVÆRæF÷væÆöEö'WGFöâ€Ğ¢.h›˜xşKˆ¾‹ÛŞiÊÎjÊXZ˜:{¹>iéÂ"ÀĞ¢&6†—fUöFFÀĞ¢f–ÆUöæÖSÖb'µ÷6fUöf–ÆVæÖR†FWF–Âç'VâçF&vWE÷&öGV7B—Ò×¶FWF–Âç'Vâæ–E³£…×Òç¦—"ÀĞ¢Ö–ÖSÒ&Æ–6F–öâ÷¦—"ÀĞ¢–6öãÒ#¦ÖFW&–Âö&6†—fS¢"ÀĞ¢Ğ¢–bFWF–Âç&W7VÇBævWB‚&FW6–vå÷FW‡B"“ Ğ¢v—F‚7EöÖöGVÆRæW‡æFW"‚.ŠëîŠêikjš(NŠx‚"ÂW‡æFVCÕG'VR“ Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‡7G"†FWF–Âç&W7VÇE²&FW6–vå÷FW‡B%Ò’Ğ¢–bÆöFVEöFWF–Åö–BÓÒ6VÆV7FVEö–C Ğ¢f÷"'F–f7B–âFWF–Âæ'F–f7G3 Ğ¢v—F‚7EöÖöGVÆRæW‡æFW"†b'¶'F–f7BææÖWÒ+r¶'F–f7Bç6—¦Uö'—FW2ò#C¢ãgÒ´""“ Ğ¢÷&VæFW%ö'F–f7B‡7EöÖöGVÆRÂ'F–f7BĞ Ğ¢v—F‚7EöÖöGVÆRæW‡æFW"‚.ZûjùNKŠNKŠ®x˜iÊÂ"ÂW‡æFVCÔfÇ6R“ Ğ¢6ö×&Uö–G2Ò7EöÖöGVÆRæ×VÇF—6VÆV7B€Ğ¢.˜hºKŠNKŠ®x˜iÊÂ"ÀĞ¢·'Vâæ–Bf÷"'Vâ–â'Vç5ÒÀĞ¢Ö…÷6VÆV7F–öç3Ó"ÀĞ¢f÷&ÖEögVæ3ÖÆÖ&F'Våö–C¢€Ğ¢b'¶÷F–öç5·'Våö–EÒçWFFVEöE³£•Òç&WÆ6R‚uBrÂrr—Ò+r¶÷F–öç5·'Våö–EÒæÖöFVÇÒ Ğ¢’ÀĞ¢Ğ¢–bÆVâ†6ö×&Uö–G2’ÓÒ# Ğ¢6ö×&Uö6öÇVÖç2Ò7EöÖöGVÆRæ6öÇVÖç2ƒ"Ğ¢f÷"6öÇVÖâÂ'Våö–B–â¦—†6ö×&Uö6öÇVÖç2Â6ö×&Uö–G2“ Ğ¢6ö×&VBÒö66†VE÷'VåöFWF–Â††—7F÷'’Â'Våö–BÂfÇ6RĞ¢v—F‚6öÇVÖã Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ†b"¢§¶6ö×&VBç'VâçWFFVEöE³£•Òç&WÆ6R‚uBrÂrr—Ò¢¢"Ğ¢7EöÖöGVÆRæ6F–öâ€Ğ¢b'¶6ö×&VBç'Vâç7FGW2çfÇVWÒ+r¶6ö×&VBç'VâæÖöFVÇÒ+r‹J˜xşXˆb¶6ö×&VBçVÆ—G•÷66÷&S¢ãgÒ Ğ¢Ğ¢7EöÖöGVÆRçw&—FR†6ö×&VBç'VâæFVÖæE÷FW‡BĞ¢FW6–våöW†6W'BÒ7G"†6ö×&VBç&W7VÇBævWB‚&FW6–vå÷FW‡B"’÷".i¨.izŠëîŠêih~iÊÂ"Ğ¢7EöÖöGVÆRçw&—FR†FW6–våöW†6W'E³£#ÒĞ Ğ¢v—F‚7EöÖöGVÆRæW‡æFW"‚.™Èk.KˆîŠøNŠë®ŠøhÚâ"ÂW‡æFVCÔfÇ6R“ Ğ¢Wf–FVæ6RÒ&W÷6—F÷'’æÆ—7E÷&öGV7EöWf–FVæ6R†7F—fRÂÆ–Ö—CÓ#Ğ¢–bWf–FVæ6U²'&WV—&VÖVçG2%Ó Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"¢®™Èk.ŠøhÚâ¢¢"Ğ¢7EöÖöGVÆRæFFg&ÖR†Wf–FVæ6U²'&WV—&VÖVçG2%ÒÂ†–FUö–æFWƒÕG'VRÂW6Uö6öçF–æW%÷v–GFƒÕG'VRĞ¢–bWf–FVæ6U²&6öÖÖVçG2%Ó Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"¢®XéşZx¾ŠøNŠë¢¢¢"Ğ¢7EöÖöGVÆRæFFg&ÖR†Wf–FVæ6U²&6öÖÖVçG2%ÒÂ†–FUö–æFWƒÕG'VRÂW6Uö6öçF–æW%÷v–GFƒÕG'VRĞ¢–bæ÷BWf–FVæ6U²'&WV—&VÖVçG2%ÒæBæ÷BWf–FVæ6U²&6öÖÖVçG2%Ó Ğ¢7EöÖöGVÆRæ6F–öâ‚.[Ù>X˜ŞKª~Y8i¨.izXúş‹ûŞkªşŠøhÚî8""Ğ Ğ¢7EöÖöGVÆRæF—f–FW"‚Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"2222h.ZHŞ{¹>iéÎ[Ù.j2"Ğ¢&W7F÷&U÷&öGV7G2Ò¶—FVÒææÖRf÷"—FVÒ–âö66†VE÷&öGV7G2‡&W÷6—F÷'’•ĞĞ¢–b&W7F÷&U÷&öGV7G3 Ğ¢&W7F÷&U÷&öGV7BÒ7EöÖöGVÆRç6VÆV7F&÷‚€Ğ¢.h.ZHŞX‹Kª~Y8"ÀĞ¢&W7F÷&U÷&öGV7G2ÀĞ¢–æFWƒ×&W7F÷&U÷&öGV7G2æ–æFW‚†7F—fR’–b7F—fR–â&W7F÷&U÷&öGV7G2VÇ6RÀĞ¢Ğ¢VÇ6S Ğ¢&W7F÷&U÷&öGV7BÒ7EöÖöGVÆRçFW‡Eö–çWB‚.h.ZHŞX‹Kª~Y8"ÂÆ6V†öÆFW#Ò.Z¾Xi[Ù.j>h˜[îKª~Y8"Ğ¢&6†—fU÷WÆöBÒ7EöÖöGVÆRæf–ÆU÷WÆöFW"€Ğ¢.Kˆ®KÊ¤•[Ù.j2"ÀĞ¢G—SÕ²'¦—%ÒÀĞ¢¶W“Ò'c%ö&6†—fU÷&W7F÷&R"ÀĞ¢†VÇÒ.KÉ®XXj8iú^‹zş[èN8iÚyºîi[8[^[ÈZJ~[ş8Xè¾{ÊjùNY(Îih~K»n{¾Yè¾8""ÀĞ¢Ğ¢–b&6†—fU÷WÆöC Ğ¢&6†—fUö'—FW2Ò&6†—fU÷WÆöBævWGfÇVR‚Ğ¢G'“ Ğ¢Öæ–fW7BÒ–ç7V7Eö&6†—fR†&6†—fUö'—FW2Â&6†—fTÆ–Ö—G2æFVfVÇB‚’Ğ¢7EöÖöGVÆRç7V66W72€Ğ¢b.ZèXZj8iú^˜	®‹ø~ûÉ§¶ÆVâ†Öæ–fW7BæVçG&–W2—ÒKŠ®ih~K»nûÈÎ[^[ÈYâ¶Öæ–fW7BçF÷FÅ÷Væ6ö×&W76VBò#Bò#C¢ãgÒÔ.8" Ğ¢Ğ¢W†6WBVç6fT&6†—fR2W†3 Ğ¢7EöÖöGVÆRæW'&÷"‡7G"†W†2’Ğ¢&WGW&àĞ¢–b7EöÖöGVÆRæ'WGFöâ€Ğ¢.[Ù.j>K‹®iky¨NXènXû.Šë[ÙR"ÀĞ¢–6öãÒ#¦ÖFW&–Â÷Væ&6†—fS¢"ÀĞ¢F—6&ÆVCÖæ÷B7G"‡&W7F÷&U÷&öGV7B’ç7G&—‚’ÀĞ¢“ Ğ¢F–vW7BÒ†6†Æ–"ç6†#Sb†&6†—fUö'—FW2’æ†W†F–vW7B‚Ğ¢'VâÒ&W÷6—F÷'’æ7&VFU÷—VÆ–æU÷'Vâ€Ğ¢7&VFU'Vä6öÖÖæB‡7G"‡&W7F÷&U÷&öGV7B’ç7G&—‚’Â.ZèXZ‚¤•[Ù.j>h.ZHÒ"Â&&6†—fR"Â'&W7F÷&VB"Â’ÀĞ¢–FV×÷FVæ7•ö¶W“Öb'&W7F÷&S§·&W7F÷&U÷&öGV7GÓ§¶F–vW7GÒ"ÀĞ¢Ğ¢ö–çfÆ–FFU÷f–Wuö66†R‡&W÷6—F÷'’Ğ¢v—F‚FV×f–ÆRåFV×÷&'”F—&V7F÷'’‚’2FV×öF—# Ğ¢F&vWBÒF‚‡FV×öF—"Ğ¢W‡G&7Eö&6†—fR†&6†—fUö'—FW2ÂF&vWBÂ&6†—fTÆ–Ö—G2æFVfVÇB‚’Ğ¢f÷"F‚–âF&vWBç&vÆö"‚"¢"“ Ğ¢–bæ÷BF‚æ—5öf–ÆR‚“ Ğ¢6öçF–çVPĞ¢FFÒF‚ç&VEö'—FW2‚Ğ¢æÖRÒ÷6fUöf–ÆVæÖR‡F‚ææÖRĞ¢Ö–ÖRÒÖ–ÖWG—W2æwVW75÷G—R†æÖR•³Ò÷"&Æ–6F–öâöö7FWB×7G&VÒ Ğ¢7F÷&VBÒ7F÷&RçWB‡'Vâæ–BÂæÖRÂFFÂÖ–ÖRĞ¢&W÷6—F÷'’ç&V6÷&Eö'F–f7B‡'Vâæ–BÂö'F–f7Eö¶–æB†æÖRÂÖ–ÖR’Â7F÷&VBĞ¢7EöÖöGVÆRç6W76–öå÷7FFU²'c%ö7W'&VçE÷'Våö–B%ÒÒ'Vâæ–@Ğ¢÷6WEö7F—fU÷&öGV7B‡7EöÖöGVÆRÂ'VâçF&vWE÷&öGV7BĞ¢7EöÖöGVÆRç6W76–öå÷7FFU²'c%ö7W'&VçE÷'Våö–B%ÒÒ'Vâæ–@Ğ¢ö–çfÆ–FFU÷f–Wuö66†R‡&W÷6—F÷'’Ğ¢7EöÖöGVÆRç7V66W72‚.[Ù.j>[{.h.ZHŞX‹xºÎz¸²c"XènXû.Šë[Ù^8""Ğ Ğ Ğ¦FVböÖ–w&F–öå÷6W'f–6R€Ğ¢6öæf–s¢6öæf–rÀĞ¢&W÷6—F÷'“¢¶æ÷vÆVFvU&W÷6—F÷'’ÀĞ¢7F÷&S¢ö&¦V7BÀĞ¢’ÓâÖ–w&F–öå6W'f–6S Ğ¢&ö÷G2Ò°Ğ¢…$ôõBòfÇVR’ç&W6öÇfR‚’–bæ÷BF‚‡fÇVR’æ—5ö'6öÇWFR‚’VÇ6RF‚‡fÇVRĞ¢f÷"fÇVR–â6öæf–ræÆVv7•ö÷WGWE÷&ö÷G0Ğ¢ĞĞ¢&WGW&âÖ–w&F–öå6W'f–6R€Ğ¢ÆVv7•&VFW"†6öæf–ræÆVv7•öFF&6U÷W&ÂÂ÷væW%ö–CÒ'&—fFR"Â÷WGWE÷&ö÷G3×&ö÷G2’ÀĞ¢&W÷6—F÷'’ÀĞ¢7F÷&RÀĞ¢Ğ Ğ Ğ¦FVb÷&VæFW%÷6WGF–æw2€Ğ¢7EöÖöGVÆS¢ö&¦V7BÀĞ¢6öæf–s¢6öæf–rÀĞ¢&W÷6—F÷'“¢¶æ÷vÆVFvU&W÷6—F÷'’ÀĞ¢7F÷&S¢ö&¦V7BÀĞ¢’ÓâæöæS Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"222Šëî{ÚîKˆî‹øz{²"Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"2222y›îx+ÎiXiéÎY»â¶W’˜XŞ{Úâ"Ğ¢v—F‚7EöÖöGVÆRæ6öçF–æW"†&÷&FW#ÕG'VR“ Ğ¢–b6öæf–ræ–ÖvUö•ö¶W“ Ğ¢7EöÖöGVÆRç7V66W72‚.™‹ş˜xÎK©y›îx+ÎiXiéÎY»â¶W’[{.˜XŞ{Úî8.š^™Ú.KˆŞKÉ®i‹îzK®h‰nY¹îKÊXéşXÎ8""Ğ¢VÇ6S Ğ¢7EöÖöGVÆRçv&æ–ær‚.™‹ş˜xÎK©y›îx+ÎiXiéÎY»â¶W’[	®iÊ®˜XŞ{ÚîûÈÄ’iXiéÎY»îyIşh‰i¨.KˆŞXúşyJ8""Ğ¢7EöÖöGVÆRæ6F–öâ€Ğ¢.˜XŞ{ÚîKØŞ{ÚîûÉ¥7G&VÖÆ—B6Æ÷VB(i"h‰y¨N[©NyJ‚(i"[Ù>X˜Òc"[©NyJ‚(i"6WGF–æw2(i"6V7&WG>8" Ğ¢Ğ¢7EöÖöGVÆRæ6öFR‡6V7&WEö6öæf–wW&F–öå÷FV×ÆFR†6öæf–r’ÂÆæwVvSÒ'FöÖÂ"Ğ¢7EöÖöGVÆRæÆ–æµö'WGFöâ€Ğ¢.h™>[È7G&VÖÆ—B[©NyJzêyb"ÀĞ¢&‡GG3¢ò÷6†&Rç7G&VÖÆ—Bæ–òò"ÀĞ¢–6öãÒ#¦ÖFW&–Âö÷Våö–åöæWs¢"ÀĞ¢W6Uö6öçF–æW%÷v–GFƒÕG'VRÀĞ¢Ğ¢7EöÖöGVÆRæ6F–öâ‚.KùŞZÙ‚6V7&WG2Yî[©NyJKÉ®ˆz®Xª˜xŞY
şûÉ¾˜xŞiky›¾[Ù^XÛ>XúşyIşh‰y›îx+ÎiXiéÎY»î8""Ğ Ğ¢7EöÖöGVÆRæF—f–FW"‚Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"2222iÈŞXª˜XŞ{ÚîûÈ[{.ˆKiXşûÈ’"Ğ¢7EöÖöGVÆRçF&ÆR€Ğ¢·².iÈŞXª#¢æÖRÂ.x«nh#¢fÇVWÒf÷"æÖRÂfÇVR–âÖ6¶VE÷6W'f–6U÷7VÖÖ'’†6öæf–r’æ—FV×2‚•ĞĞ¢Ğ¢–b7EöÖöGVÆRæ'WGFöâ‚.j8iú^i[hÚî[©>‹ùîhêR"Â–6öãÒ#¦ÖFW&–ÂöFF&6S¢"“ Ğ¢G'“ Ğ¢6÷VçG2Ò°Ğ¢æÖS¢&W÷6—F÷'’æ6÷VçE÷&÷w2†æÖRĞ¢f÷"æÖR–â‚'&öGV7G2"Â&6öÖÖVçG2"Â'&WV—&VÖVçG2"Â'—VÆ–æU÷'Vç2"Â&'F–f7G2"Ğ¢ĞĞ¢7EöÖöGVÆRç7V66W72†b.‹ùîhê^jÚ>[‹ûÉ§¶6÷VçG7Ò"Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢7EöÖöGVÆRæW'&÷"‡V&Æ–5öW'&÷%öÖW76vR‚.‹ùîhê^j8iú^ZK‹JR"ÂW†2’Ğ Ğ¢7EöÖöGVÆRæF—f–FW"‚Ğ¢7EöÖöGVÆRæÖ&¶F÷vâ‚"2222zêynY[z^X[r+rXéşz¹i[hÚîZHŞX‹b"Ğ¢7EöÖöGVÆRæ6F–öâ‚.‹øz{¾˜x~yJXXš(NkÉN8XhŞZHŞX‹n8iÈYîj
š¨ÎûÉ¾KˆŞKÉ®KúîiKh‰nXŠ™šNXéşz¹i[hÚî8.Xúş˜xŞZHŞhš~ŠÎK‰NKˆŞKÉ®˜xŞZHŞZûÎXZ^8""Ğ¢–bæ÷B6öæf–ræÆVv7•öFF&6U÷W&ÂæBæ÷B6öæf–ræÆVv7•ö÷WGWE÷&ö÷G3 Ğ¢7EöÖöGVÆRæ–æfò‚.[	®iÊ®˜XŞ{Úâc%ôÄTt5•ôDD$4UõU$Âòc%ôÄTt5•ôõUEUEõ$ôõE>8.Xéşz¹KùŞhÈKˆŞXù8""Ğ¢&WGW&àĞ¢6W'f–6RÒöÖ–w&F–öå÷6W'f–6R†6öæf–rÂ&W÷6—F÷'’Â7F÷&RĞ¢f—'7BÂ6V6öæBÂF†—&BÒ7EöÖöGVÆRæ6öÇVÖç2ƒ2Ğ¢–bf—'7Bæ'WGFöâ‚#â‹øz{¾š(NkÉB"Â–6öãÒ#¦ÖFW&–Âöf7Eö6†V6³¢"“ Ğ¢G'“ Ğ¢&W÷'BÒ6W'f–6RæG'•÷'Vâ‚Ğ¢7EöÖöGVÆRç6W76–öå÷7FFU²'c%öÖ–w&F–öå÷&W÷'B%ÒÒ&W÷'@Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢7EöÖöGVÆRæW'&÷"‡V&Æ–5öW'&÷%öÖW76vR‚.š(NkÉNZK‹JR"ÂW†2’Ğ¢Ç•ö6öæf—&ÖVBÒ7EöÖöGVÆRæ6†V6¶&÷‚‚.zîŠêNK¸^ZHŞX‹ni[hÚîûÈÎKˆŞi»NiKXéşz¹’"Â¶W“Ò'c%öÖ–w&F–öåö6öæf—&Ò"Ğ¢–b6V6öæBæ'WGFöâ‚#"â[ÈZx¾ZHŞX‹b"Â–6öãÒ#¦ÖFW&–Âö6öçFVçEö6÷“¢"ÂF—6&ÆVCÖæ÷BÇ•ö6öæf—&ÖVB“ Ğ¢G'“ Ğ¢&W÷'BÒ6W'f–6RæÇ’‚Ğ¢7EöÖöGVÆRç6W76–öå÷7FFU²'c%öÖ–w&F–öå÷&W÷'B%ÒÒ&W÷'@Ğ¢7EöÖöGVÆRç7V66W72†b.ZHŞX‹nZèÎh‰ûÉ®ikZ)â·&W÷'BæÖ–w&FVE÷F÷FÇÒšûÈÎ‹{>‹ør·&W÷'Bç6¶—VE÷F÷FÇÒš8""Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢7EöÖöGVÆRæW'&÷"‡V&Æ–5öW'&÷%öÖW76vR‚.ZHŞX‹nZK‹JR"ÂW†2’Ğ¢f–æÆÇ“ Ğ¢ö–çfÆ–FFU÷f–Wuö66†R‡&W÷6—F÷'’Ğ¢–bF†—&Bæ'WGFöâ‚#2âY8[ˆÎj
š¨Â"Â–6öãÒ#¦ÖFW&–Â÷fW&–f–VC¢"“ Ğ¢G'“ Ğ¢fW&–f–6F–öâÒ6W'f–6RçfW&–g’‚Ğ¢–bfW&–f–6F–öâæ6öç6—7FVçC Ğ¢7EöÖöGVÆRç7V66W72†b.j
š¨Î˜	®‹ø~ûÈÎ[{.jš¨Â·fW&–f–6F–öâæ6†V6¶VEöf–ÆW7ÒKŠ®Xéşz¹ih~K»n8""Ğ¢VÇ6S Ğ¢7EöÖöGVÆRæW'&÷"‚.j
š¨ÎiÊ®˜	®‹ø~ûÉ¢"².ûÉ²"æ¦ö–â‡fW&–f–6F–öâæf–ÆVEö6†V6·2’Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢7EöÖöGVÆRæW'&÷"‡V&Æ–5öW'&÷%öÖW76vR‚.j
š¨ÎZK‹JR"ÂW†2’Ğ¢&W÷'BÒ7EöÖöGVÆRç6W76–öå÷7FFRævWB‚'c%öÖ–w&F–öå÷&W÷'B"Ğ¢–b&W÷'C Ğ¢7EöÖöGVÆRæ§6öâ€Ğ¢°Ğ¢.jŠ[Èò#¢&W÷'BæÖöFRÀĞ¢.k©i[hÚâ#¢&W÷'Bç6÷W&6Uö6÷VçG2ÀĞ¢%c"[Ù>X˜Şi[hÚâ#¢&W÷'BçF&vWEö6÷VçG2ÀĞ¢.ikZ)â#¢&W÷'BæÖ–w&FVBÀĞ¢.‹{>‹ør#¢&W÷'Bç6¶—VBÀĞ¢ĞĞ¢Ğ Ğ Ğ¦FVbÖ–â‚’ÓâæöæS Ğ¢–×÷'B7G&VÖÆ—B27@Ğ Ğ¢7Bç6WE÷vUö6öæf–r€Ğ¢vU÷F—FÆSÒ.Kª~Y8ŠøNŠë®yú^Šøn[©>i›®ˆ;ŞKÙ2c""ÀĞ¢vUö–6öãÒ$’"ÀĞ¢Æ–÷WCÒ'v–FR"ÀĞ¢–æ—F–Å÷6–FV&%÷7FFSÒ&W‡æFVB"ÀĞ¢Ğ¢–æ¦V7E÷F†VÖR‡7BĞ¢G'“ Ğ¢6öæf–rÒ6öæf–ræg&öÕöÖ–ær…ö6öæf–u÷fÇVW2‡7B’Ğ¢W†6WB6öæf–tW'&÷"2W†3 Ğ¢7BæW'&÷"†b%c"[	®iÊ®ZèÎh‰iÈŞXªzºş˜XŞ{ÚîûÉ§¶W†7Ò"Ğ¢7Bæ6öFR€Ğ¢%c%õU4U$äÔRÒÂ&÷væW%Â%Æâ Ğ¢%c%õ55tõ$Eô„4‚ÒÂ'67'—BBââåÂ%Æâ Ğ¢%c%ôDD$4UõU$ÂÒÂ'÷7Fw&W7Ã¢òòââåÂ""ÀĞ¢ÆæwVvSÒ'FöÖÂ"ÀĞ¢Ğ¢7Bæ6F–öâ‚.Šû~YÊik7G&VÖÆ—B[©NyJy¨B6V7&WG2KŠŞ˜XŞ{Úî8.Xéşz¹KˆŞXù~[ÛY8Ş8""Ğ¢&WGW&àĞ Ğ¢–bæ÷BöWF†VçF–6FVB‡7BÂ6öæf–r“ Ğ¢÷&VæFW%öÆöv–â‡7BÂ6öæf–rĞ¢&WGW&àĞ Ğ¢7Bç6W76–öå÷7FFU²&Æöv–å÷W6W&æÖR%ÒÒ" Ğ¢7Bç6W76–öå÷7FFU²&Æöv–å÷77v÷&B%ÒÒ" Ğ Ğ¢G'“ Ğ¢&W÷6—F÷'’Ò÷&W÷6—F÷'•öf÷"†6öæf–rĞ¢7F÷&RÒ÷7F÷&Uöf÷"†6öæf–rÂ&W÷6—F÷'’Ğ¢W†6WBW†6WF–öâ2W†3 Ğ¢7BæW'&÷"€Ğ¢V&Æ–5öW'&÷%öÖW76vR€Ğ¢.zxiÈiÈŞXªX‰ŞZx¾XÉnZK‹JR"ÀĞ¢W†2ÀĞ¢wV–Fæ6SÒ.Šû~j8iú^‹ùîhê^YËYØ8i[hÚî[©>Zønzh‰b7W&6R‹ùîhê^kXzŞhÚî8""ÀĞ¢Ğ¢Ğ¢7Bæ6F–öâ‚.iÊ®ˆz®XªY¹î˜X‹XZÎX[i[hÚî[©>h‰nXZÎX[ZÙX*8""Ğ¢&WG'•ö6öÂÂÖævUö6öÂÒ7Bæ6öÇVÖç2ƒ"Ğ¢–b&WG'•ö6öÂæ'WGFöâ‚.˜xŞik‹ùîhê^zxiÈiÈŞXª"ÂG—SÒ'&–Ö'’"ÂW6Uö6öçF–æW%÷v–GFƒÕG'VR“ Ğ¢ö–çfÆ–FFU÷f–Wuö66†R‚Ğ¢7Bç&W'Vâ‚Ğ¢ÖævUö6öÂæÆ–æµö'WGFöâ€Ğ¢.h™>[È7G&VÖÆ—B[©NyJzêyb"ÀĞ¢&‡GG3¢ò÷6†&Rç7G&VÖÆ—Bæ–òò"ÀĞ¢W6Uö6öçF–æW%÷v–GFƒÕG'VRÀĞ¢Ğ¢v—F‚7BæW‡æFW"‚.‹ùîhê^KúîZHŞj8iú^š’"ÂW‡æFVCÕG'VR“ Ğ¢7BæÖ&¶F÷vâ€Ğ¢#âYÊ[©NyJ‚6V7&WG2KŠŞ˜xŞik{)‹KNZèÎi[Bc%ôDD$4UõU$Æ8%Æâ Ğ¢#"âZønzY
²8¦8ö86zØZÙ~zÊni{nûÈÎKÛşyJ‚7W&6RZHŞX‹nX{®y¨NZèÎi[BU$8%Æâ Ğ¢#2â7G&VÖÆ—B6Æ÷VBKÉXXKÛşyJ‚7W&6RG&ç67F–öâööÆW.ûÈzºşXú2cSC>ûÈ8%Æâ Ğ¢#BâKùŞZÙYîzØ[è^[©NyJ˜xŞY
şûÈÎXhŞx+X{¾Kˆ®ik˜xŞik‹ùîhê^8" Ğ¢Ğ¢&WGW&àĞ Ğ¢†—7F÷'’Ò†—7F÷'•6W'f–6R‡&W÷6—F÷'’Â7F÷&R¢æf–vF–öâÒ÷&VæFW%÷6–FV&"‡7BÂ6öæf–r¢æf–vF–öâÒ÷&VæFW%öÖö&–ÆUöæf–vF–öâ‡7B¢7F—fRÒö7F—fU÷&öGV7B‡7B¢æf–vF–öå÷6æ6†÷BÒ÷v÷&·76U÷6æ6†÷B‡&W÷6—F÷'’Â7F—fR’–b7F—fRVÇ6Rõv÷&·76Uf–Wr‚¢6æ6†÷BÒ€¢÷v÷&·76U÷6æ6†÷B‡&W÷6—F÷'’¢–bæf–vF–öâÓÒ.yú^Šøn[©>jh.Šx‚ ¢VÇ6Ræf–vF–öå÷6æ6†÷@¢¢÷&VæFW%ö†VFW"‡7BÂ6öæf–rÂæf–vF–öå÷6æ6†÷BÂæf–vF–öâĞ Ğ¢–bæf–vF–öâÓÒ.ZûÎXZ^ŠøNŠë®‹XNKªr# Ğ¢÷&VæFW%ö–×÷'B‡7BÂ6öæf–rÂ&W÷6—F÷'’Â7F÷&RĞ¢VÆ–bæf–vF–öâÓÒ.™Èk.yIşh‰# Ğ¢÷&VæFW%öFVÖæB‡7BÂ6öæf–rÂ&W÷6—F÷'’Â7F÷&RĞ¢VÆ–bæf–vF–öâÓÒ.yú^Šøn[©>jh.Šx‚# Ğ¢÷&VæFW%ö÷fW'f–Wr‡7BÂ&W÷6—F÷'’Â†—7F÷'’Â6æ6†÷BĞ¢VÆ–bæf–vF–öâÓÒ.™Èk"ŞX©şˆ;ÒŞ{¹>ièNY»î‹# Ğ¢÷&VæFW%öw&‚‡7BÂ†—7F÷'’Ğ¢VÆ–bæf–vF–öâÓÒ.ŠëîŠêikj‚# Ğ¢÷&VæFW%öFW6–vâ‡7BÂ†—7F÷'’Ğ¢VÆ–bæf–vF–öâÓÒ.[z^K‰®ŠëîŠê&ö×B# Ğ¢÷&VæFW%÷&ö×B‡7BÂ†—7F÷'’Ğ¢VÆ–bæf–vF–öâÓÒ$’iXiéÎY»â# Ğ¢÷&VæFW%ö–ÖvW2‡7BÂ6öæf–rÂ&W÷6—F÷'’Â7F÷&RÂ†—7F÷'’Ğ¢VÆ–bæf–vF–öâÓÒ.XènXû.Šë[ÙR# Ğ¢÷&VæFW%ö†—7F÷'’‡7BÂ&W÷6—F÷'’Â7F÷&RÂ†—7F÷'’Ğ¢VÇ6S Ğ¢÷&VæFW%÷6WGF–æw2‡7BÂ6öæf–rÂ&W÷6—F÷'’Â7F÷&RĞ Ğ Ğ¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ğ¢Ö–â‚Ğ