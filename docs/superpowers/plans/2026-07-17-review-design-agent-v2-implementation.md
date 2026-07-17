# 产品评论知识库智能体 V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改原站入口和原数据的前提下，交付具备单用户私有登录、独立数据库与文件空间、完整旧功能、历史迁移和深色科技界面的 V2 Streamlit 应用。

**Architecture:** `v2/` 使用 auth、application、adapters、pipeline、providers、ui 六个边界清晰的模块；服务器端连接 `agent_v2` schema 和私有 Storage，原 schema 与旧文件只通过只读迁移适配器访问。UI 只调用应用服务，所有运行、阶段和资产都有持久化记录与 UUID。

**Tech Stack:** Python 3.11+、Streamlit 1.58、pandas、psycopg 3.2、Supabase PostgreSQL/Storage HTTP API、现有分析脚本、unittest、Streamlit AppTest、Chromium 视觉验收。

## Global Constraints

- 原 `app.py`、`app_legacy_current.py` 和 `pages/` 保持行为不变。
- V2 使用同一 Supabase 项目的私有 `agent_v2` schema 与独立私有 bucket。
- 登录前不允许初始化或读取业务数据。
- 页面不接受或回显原始 API Key；密钥仅来自 Secrets。
- 原主站和旧版十阶段全部功能、结果、效果图、下载和归档必须保留。
- 每项生产代码严格执行 RED → GREEN → REFACTOR。
- 不提交、推送、部署、删除原数据；外部发布动作留到验证完成后按用户既有授权执行。
- 不覆盖现有未跟踪 `.playwright-cli/` 和 `output/wan27-*.png`。
- 视觉目标为用户提供的深色科技控制台截图；桌面 1440×1000、移动 390×844。

---

### Task 1: 冻结原站与建立 V2 配置/登录核心

**Files:**
- Create: `v2/__init__.py`
- Create: `v2/config.py`
- Create: `v2/auth.py`
- Create: `v2/security.py`
- Create: `tests/v2/test_auth.py`
- Create: `tests/v2/test_config.py`

**Interfaces:**
- Produces: `AppConfig.from_mapping(values) -> AppConfig`
- Produces: `hash_password(password, salt=None) -> str`
- Produces: `verify_password(password, encoded_hash) -> bool`
- Produces: `LoginGuard.authenticate(username, password, now) -> AuthDecision`
- Produces: `SessionClock.is_expired(last_activity, now) -> bool`

- [ ] **Step 1: 保存原站冻结基线**

Run:
```powershell
git hash-object app.py app_legacy_current.py pages\01_现有流程备份.py pages\02_产品管理.py pages\03_旧版结果预览.py
```
Expected: 输出 5 个哈希；保存到测试常量，最终再次核对。

- [ ] **Step 2: 写配置和登录失败测试**

```python
class AuthTests(unittest.TestCase):
    def test_password_hash_round_trip_and_wrong_password_rejected(self):
        encoded = hash_password("correct horse")
        self.assertTrue(verify_password("correct horse", encoded))
        self.assertFalse(verify_password("wrong", encoded))

    def test_five_failures_lock_login_for_fifteen_minutes(self):
        guard = LoginGuard("owner", hash_password("secret"), max_failures=5, cooldown_seconds=900)
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        for _ in range(5):
            guard.authenticate("owner", "wrong", now)
        self.assertEqual(guard.authenticate("owner", "secret", now).status, "locked")

    def test_session_expires_after_eight_hours_inactivity(self):
        self.assertTrue(SessionClock(28800).is_expired(0, 28801))
```

- [ ] **Step 3: 运行测试并确认因模块缺失失败**

Run: `python -m unittest tests.v2.test_auth tests.v2.test_config -v`
Expected: FAIL/ERROR，仅因为 `v2.auth`、`v2.config` 尚未存在。

- [ ] **Step 4: 实现最小登录与配置核心**

```python
@dataclass(frozen=True)
class AppConfig:
    username: str
    password_hash: str
    database_url: str
    schema: str = "agent_v2"
    storage_bucket: str = "agent-v2-private"

def hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=actual_salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${actual_salt.hex()}${digest.hex()}"
```

`verify_password` 必须解析格式、重新计算并使用 `hmac.compare_digest`；错误格式返回 `False`。配置缺少用户名、密码哈希或数据库连接时返回可读配置错误，不回显敏感值。

- [ ] **Step 5: 运行登录测试与全量回归**

Run: `python -m unittest tests.v2.test_auth tests.v2.test_config -v`
Expected: PASS。
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: 现有测试无新增失败。

### Task 2: 独立 schema、领域模型与知识库仓储

**Files:**
- Create: `v2/domain/__init__.py`
- Create: `v2/domain/models.py`
- Create: `v2/adapters/__init__.py`
- Create: `v2/adapters/postgres.py`
- Create: `v2/migrations/001_agent_v2_schema.sql`
- Create: `tests/v2/test_repository.py`
- Create: `tests/v2/test_schema_sql.py`

**Interfaces:**
- Produces: `RunStatus`, `ArtifactKind`, `PipelineRun`, `ArtifactRecord`
- Produces: `KnowledgeRepository.initialize() -> None`
- Produces: `KnowledgeRepository.ingest_comments(...) -> ImportReport`
- Produces: `KnowledgeRepository.create_pipeline_run(command, idempotency_key) -> PipelineRun`
- Produces: `KnowledgeRepository.list_products()`, `list_runs()`, `get_run()`

- [ ] **Step 1: 写 schema 与仓储失败测试**

```python
def test_duplicate_comments_and_requirements_are_idempotent(self):
    repo = sqlite_repository(self.temp_dir)
    first = repo.ingest_comments("智能药盒", "适老健康", "a.csv", ["提醒明显", "提醒明显"])
    second = repo.ingest_comments("智能药盒", "适老健康", "b.csv", ["提醒明显"])
    self.assertEqual(first.inserted_count, 1)
    self.assertEqual(second.inserted_count, 0)
    self.assertEqual(repo.count_requirements(), 1)

def test_same_idempotency_key_returns_existing_run(self):
    first = repo.create_pipeline_run(command, "stable-key")
    second = repo.create_pipeline_run(command, "stable-key")
    self.assertEqual(first.id, second.id)
```

SQL 静态测试必须断言包含 `CREATE SCHEMA IF NOT EXISTS agent_v2`、9 张核心表、外键、指纹唯一索引、RLS、撤销 `anon/authenticated` 权限。

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_repository tests.v2.test_schema_sql -v`
Expected: FAIL，因为仓储和 SQL 尚未实现。

- [ ] **Step 3: 实现领域状态与 SQLite/PostgreSQL 双适配仓储**

```python
class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DELETING = "deleting"

@dataclass(frozen=True)
class ImportReport:
    product_id: int
    batch_id: int
    input_count: int
    inserted_count: int
    duplicate_count: int
    requirement_count: int
```

连接 PostgreSQL 后执行 `SET search_path TO agent_v2, public`；所有 SQL 参数化。SQLite 仅用于本地与测试，使用同结构表名且不接触原 `data/product_knowledge_base.sqlite3`。

- [ ] **Step 4: 实现安全 SQL**

SQL 创建 `products`、`comment_batches`、`comments`、`requirements`、`generation_runs`、`pipeline_runs`、`stage_runs`、`artifacts`、`migration_ledger`、`login_audit`；schema 不暴露到 Data API，撤销公共角色访问，开启 RLS 并添加固定服务器所有者策略/拒绝公共策略。

- [ ] **Step 5: 验证仓储、SQL 和回归**

Run: `python -m unittest tests.v2.test_repository tests.v2.test_schema_sql -v`
Expected: PASS。
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: PASS。

### Task 3: 私有资产存储、归档安全与完整删除

**Files:**
- Create: `v2/adapters/storage.py`
- Create: `v2/application/artifacts.py`
- Create: `v2/application/deletion.py`
- Create: `tests/v2/test_storage.py`
- Create: `tests/v2/test_safe_archive.py`
- Create: `tests/v2/test_deletion.py`

**Interfaces:**
- Produces: `ArtifactStore.put(run_id, name, data, mime) -> StoredArtifact`
- Produces: `ArtifactStore.read(path) -> bytes`
- Produces: `ArtifactStore.delete_many(paths) -> DeleteReport`
- Produces: `inspect_archive(data, limits) -> ArchiveManifest`
- Produces: `DeletionService.plan_product(product_id) -> DeletionPlan`
- Produces: `DeletionService.execute(plan) -> DeletionResult`

- [ ] **Step 1: 写路径、ZIP 和级联删除失败测试**

```python
def test_artifacts_are_scoped_by_run_uuid(self):
    first = store.put(UUID(int=1), "效果图.png", b"one", "image/png")
    second = store.put(UUID(int=2), "效果图.png", b"two", "image/png")
    self.assertNotEqual(first.path, second.path)

def test_archive_rejects_traversal_and_extreme_compression_ratio(self):
    with self.assertRaises(UnsafeArchive):
        inspect_archive(make_zip({"../evil.txt": b"x"}), ArchiveLimits.default())

def test_delete_failure_does_not_report_success(self):
    result = service.execute(plan_with_failing_object)
    self.assertEqual(result.status, "partial")
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_storage tests.v2.test_safe_archive tests.v2.test_deletion -v`
Expected: FAIL，因为接口缺失。

- [ ] **Step 3: 实现本地/HTTP 私有 Storage 适配器与 ZIP 限制**

路径固定为 `runs/{uuid}/{safe_name}`。归档默认限制：50MB 上传、500 个条目、250MB 展开总量、50MB 单文件、100:1 压缩比；拒绝绝对路径、`..`、符号链接和未知扩展名。

- [ ] **Step 4: 实现删除计划和两阶段删除**

先计算关联计数并把运行标记为 `deleting`；删除 Storage 后事务删除元数据。Storage 失败则状态 `partial` 并保留重试信息。

- [ ] **Step 5: 验证与回归**

Run: `python -m unittest tests.v2.test_storage tests.v2.test_safe_archive tests.v2.test_deletion -v`
Expected: PASS。

### Task 4: 原数据库与历史文件的幂等迁移

**Files:**
- Create: `v2/adapters/legacy.py`
- Create: `v2/application/migration.py`
- Create: `tests/v2/test_migration.py`
- Create: `docs/V2_MIGRATION.md`

**Interfaces:**
- Produces: `LegacyReader.scan() -> LegacySnapshot`
- Produces: `MigrationService.dry_run() -> MigrationReport`
- Produces: `MigrationService.apply() -> MigrationReport`
- Produces: `MigrationService.verify() -> VerificationReport`

- [ ] **Step 1: 写 dry-run、重复迁移和孤立文件测试**

```python
def test_dry_run_never_writes(self):
    before = target.count_all()
    report = service.dry_run()
    self.assertEqual(target.count_all(), before)
    self.assertGreater(report.products, 0)

def test_apply_twice_is_idempotent(self):
    first = service.apply()
    second = service.apply()
    self.assertEqual(first.target_counts, second.target_counts)

def test_unowned_visible_files_become_legacy_snapshot(self):
    service.apply()
    self.assertEqual(target.find_artifact("legacy-snapshot", "方案评价表.xlsx").kind, "legacy")
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_migration -v`
Expected: FAIL，因为迁移服务缺失。

- [ ] **Step 3: 实现只读扫描与迁移账本**

读取原 `public` 表、`generation_runs` JSON、`output/runs`、仓库可见旧结果和安全 ZIP；每项使用 `source_type + source_id + sha256` 写入 `migration_ledger`。

- [ ] **Step 4: 实现数量/字节/哈希验证报告**

报告包含来源、目标、迁移、跳过、冲突、缺失、文件总字节和抽样哈希；任何不一致明确为 `warning` 或 `failed`，不修改来源。

- [ ] **Step 5: 验证迁移与回归**

Run: `python -m unittest tests.v2.test_migration -v`
Expected: PASS。

### Task 5: 完整十阶段能力编排到七阶段 V2

**Files:**
- Create: `v2/pipeline/__init__.py`
- Create: `v2/pipeline/catalog.py`
- Create: `v2/pipeline/runner.py`
- Create: `v2/application/imports.py`
- Create: `tests/v2/test_pipeline_catalog.py`
- Create: `tests/v2/test_pipeline_runner.py`
- Modify only if required for compatibility: `scripts/*.py`

**Interfaces:**
- Produces: `LEGACY_STAGES: tuple[StageDefinition, ...]`
- Produces: `V2_STAGES: tuple[StageGroup, ...]`
- Produces: `PipelineRunner.run_all(command) -> PipelineResult`
- Produces: `PipelineRunner.run_stage(stage_id, command) -> StageResult`

- [ ] **Step 1: 写完整功能映射和依赖失败测试**

```python
def test_every_legacy_stage_is_mapped_once(self):
    mapped = [legacy for group in V2_STAGES for legacy in group.legacy_stage_ids]
    self.assertEqual(mapped, [f"{index:02d}" for index in range(1, 11)])

def test_failed_stage_stops_dependents_but_preserves_successful_artifacts(self):
    result = runner.run_all(command)
    self.assertEqual(result.status, RunStatus.PARTIAL)
    self.assertTrue(store.exists(result.successful_artifacts[0].path))
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_pipeline_catalog tests.v2.test_pipeline_runner -v`
Expected: FAIL。

- [ ] **Step 3: 实现七阶段目录和十阶段运行器**

映射：导入=01；需求生成=主知识库检索；知识库=02/03/04；图谱=05/06；设计方案=07/08/10；Prompt=07/08 的模板与八类资产；AI 图片=09。运行器复用现有脚本命令，但为每次运行建立隔离工作目录并导入最终资产到私有 Storage。

- [ ] **Step 4: 修复必要的 V1 兼容点**

若共享脚本必须修改，先写现有 V1 行为回归测试；接口参数只新增可选项，默认行为不变。

- [ ] **Step 5: 验证编排与原测试**

Run: `python -m unittest tests.v2.test_pipeline_catalog tests.v2.test_pipeline_runner -v`
Expected: PASS。
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: PASS。

### Task 6: DeepSeek、DashScope、OpenAI、付费保护和历史恢复

**Files:**
- Create: `v2/providers/__init__.py`
- Create: `v2/providers/text.py`
- Create: `v2/providers/images.py`
- Create: `v2/application/generation.py`
- Create: `v2/application/history.py`
- Create: `tests/v2/test_providers.py`
- Create: `tests/v2/test_generation.py`
- Create: `tests/v2/test_history.py`

**Interfaces:**
- Produces: `TextProvider.generate(request) -> TextResult`
- Produces: `ImageProvider.generate(request) -> ImageResult`
- Produces: `GenerationService.preview_cost(command) -> GenerationPreview`
- Produces: `GenerationService.confirm_and_start(command, confirmation) -> PipelineRun`
- Produces: `HistoryService.reopen(run_id) -> RunDetail`

- [ ] **Step 1: 写真实/离线标记、二次确认、并发锁和历史测试**

```python
def test_offline_fallback_is_explicitly_labeled(self):
    result = provider_with_failure.generate(request)
    self.assertEqual(result.mode, "offline_fallback")

def test_paid_images_require_exact_confirmation(self):
    with self.assertRaises(ConfirmationRequired):
        service.confirm_and_start(command, confirmation=None)

def test_reopen_loads_persisted_result_not_session_state(self):
    detail = HistoryService(repo, store).reopen(saved_run.id)
    self.assertEqual(detail.artifacts[0].sha256, saved_sha)
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_providers tests.v2.test_generation tests.v2.test_history -v`
Expected: FAIL。

- [ ] **Step 3: 实现提供商适配器和脱敏错误**

DeepSeek 使用 OpenAI 兼容 Chat Completions；图片复用现有经过测试的 DashScope/OpenAI 生成函数。所有请求有超时、有限重试和错误类型，日志移除 `sk-...` 和连接串。

- [ ] **Step 4: 实现确认、锁、部分完成和历史**

确认内容必须匹配 `provider/model/count/run_nonce`；数据库唯一幂等键阻止重复启动。每张图片立即入库，失败项可单独重试。

- [ ] **Step 5: 验证**

Run: `python -m unittest tests.v2.test_providers tests.v2.test_generation tests.v2.test_history -v`
Expected: PASS。

### Task 7: 生成正式视觉资产与实现深色设计系统

**Files:**
- Create: `v2/assets/studio-background.png`
- Create: `v2/assets/assistant-mascot.png`
- Create: `v2/assets/ai-brand-mark.png`
- Create: `v2/ui/__init__.py`
- Create: `v2/ui/theme.py`
- Create: `v2/ui/components.py`
- Create: `tests/v2/test_theme.py`

**Interfaces:**
- Produces: `inject_theme() -> None`
- Produces: `render_status_header(status)`, `render_stage_nav(stage)`, `render_metric_cards(metrics)`
- Produces: responsive CSS tokens and accessible focus states

- [ ] **Step 1: 建立视觉资产清单并生成三个独立 PNG**

背景：1920×1080 深海军蓝星点/技术纹理，无文字。
助手：256×256 蓝白小型 AI 助手，深色背景适配，无文字。
品牌：128×128 发光 AI 芯片标志，无文字或只含参考图中的 `AI`。

- [ ] **Step 2: 写主题失败测试**

```python
def test_theme_has_reference_tokens_and_mobile_breakpoint(self):
    css = build_theme_css(asset_urls)
    for token in ("#030817", "#168bff", "#24d7df", "#8b5cf6", "@media (max-width: 560px)"):
        self.assertIn(token, css)
    self.assertIn(":focus-visible", css)
```

- [ ] **Step 3: 运行并确认失败**

Run: `python -m unittest tests.v2.test_theme -v`
Expected: FAIL。

- [ ] **Step 4: 实现主题与组件**

使用参考图的 312px 左栏、顶部状态胶囊、七步进度、概览卡、动作卡和结果图库。标准图标使用 Material Symbols；实际产品图来自历史/生成资产；空状态不用假缩略图。

- [ ] **Step 5: 验证主题测试**

Run: `python -m unittest tests.v2.test_theme -v`
Expected: PASS。

### Task 8: V2 Streamlit 应用与全部交互页面

**Files:**
- Create: `v2/app.py`
- Create: `v2/ui/views.py`
- Create: `v2/ui/state.py`
- Create: `tests/v2/test_app_structure.py`
- Create: `tests/v2/test_app_smoke.py`
- Modify: `requirements.txt` only if a pinned dependency is required
- Modify: `.streamlit/config.toml` only for safe V2-compatible limits

**Interfaces:**
- Consumes: Task 1–7 public interfaces
- Produces: runnable `streamlit run v2/app.py`

- [ ] **Step 1: 写登录门禁、七阶段、结果中心和惰性加载失败测试**

```python
def test_app_stops_before_repository_when_logged_out(self):
    app = AppTest.from_file("v2/app.py").run()
    self.assertTrue(any("登录" in item.value for item in app.text_input))
    self.assertFalse(any("评论沉淀" in item.value for item in app.markdown))

def test_source_contains_all_real_stage_labels(self):
    source = Path("v2/ui/views.py").read_text("utf-8")
    for label in EXPECTED_SEVEN_STAGES:
        self.assertIn(label, source)
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m unittest tests.v2.test_app_structure tests.v2.test_app_smoke -v`
Expected: FAIL。

- [ ] **Step 3: 实现登录页和控制台壳**

`app.py` 首先设置页面配置和主题，然后只执行 `render_login()`；认证成功后才创建仓储、Storage 和服务。桌面侧栏显示服务状态与掩码，顶部显示状态、时间和退出。

- [ ] **Step 4: 实现七阶段和结果中心**

使用 `st.segmented_control`/状态分支惰性渲染：导入、需求、知识库、图谱、设计评价、Prompt、图片；结果中心包含设计方案、Prompt、图片、图谱、证据、历史、下载。实现一键全流程、分阶段重跑、产品编辑/删除、归档恢复、迁移 dry-run/apply/verify。

- [ ] **Step 5: 运行 AppTest 与全量测试**

Run: `python -m unittest tests.v2.test_app_structure tests.v2.test_app_smoke -v`
Expected: PASS。
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: PASS。

### Task 9: 本地启动、桌面/移动视觉 QA、迁移演练与部署资料

**Files:**
- Create: `docs/V2_DEPLOY_STREAMLIT_CLOUD.md`
- Create: `.streamlit/secrets.v2.example.toml`
- Create: `design-qa-v2.md`
- Create: `output/v2-ui-desktop.png`
- Create: `output/v2-ui-mobile.png`
- Create: `output/v2-ui-comparison.png`

**Interfaces:**
- Produces: verified local URL and deployment instructions

- [ ] **Step 1: 生成密码哈希配置说明**

示例只写占位符：
```toml
V2_USERNAME = "owner"
V2_PASSWORD_HASH = "scrypt$..."
V2_DATABASE_URL = "postgresql://..."
V2_STORAGE_URL = "https://PROJECT.supabase.co/storage/v1"
V2_STORAGE_SERVICE_KEY = "..."
```

提供本地哈希命令，但不接收、记录或提交用户密码。

- [ ] **Step 2: 运行完整测试和语法检查**

Run: `python -m compileall v2 tests/v2`
Expected: exit 0。
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: 0 failures/errors。

- [ ] **Step 3: 启动 V2 与原站冒烟**

Run: `streamlit run v2/app.py --global.developmentMode=false --server.port=8518 --server.headless=true`
Expected: HTTP 200、无启动异常。
Run: `streamlit run app.py --global.developmentMode=false --server.port=8519 --server.headless=true`
Expected: HTTP 200、原入口可达。

- [ ] **Step 4: 浏览器视觉与交互 QA**

在用户批准的 Chromium/Playwright 环境中验证登录、导入、七阶段导航、历史、下载、删除确认和空/错/成功状态；分别截图 1440×1000 与 390×844。把参考图和实现图组合比较，修复全部 P0/P1/P2，`design-qa-v2.md` 写入 `final result: passed`。

- [ ] **Step 5: 迁移演练**

使用本地夹具执行 dry-run → apply → apply again → verify，确认来源不变、第二次无新增、计数和哈希一致。真实 Supabase 迁移仅在新应用配置 Secrets 后由私有登录用户执行。

- [ ] **Step 6: 核对原站冻结哈希与 Git 差异**

Run:
```powershell
git hash-object app.py app_legacy_current.py pages\01_现有流程备份.py pages\02_产品管理.py pages\03_旧版结果预览.py
git diff --check
git status --short
```
Expected: 原站 5 个哈希与 Task 1 一致；无空白错误；仅出现预期 V2、测试、文档和资产文件以及用户原有未跟踪文件。

- [ ] **Step 7: 部署第二个 Streamlit 应用**

在完成全部验证后，使用同仓库、主分支和 `v2/app.py` 创建独立 Streamlit Cloud 应用，配置独立 Secrets，返回新 URL；原应用和原 URL 保持运行。若当前环境没有 Streamlit Cloud/GitHub 登录权限，交付完整部署资料并明确唯一外部阻塞，不伪装已部署。

## Plan Self-Review

- Spec coverage：登录、独立 schema/bucket、全功能矩阵、十到七阶段映射、迁移、历史、删除、付费保护、深色 UI、移动端、QA 与部署均有对应任务。
- Placeholder scan：无 TBD/TODO/“稍后实现”等占位语句。
- Type consistency：`PipelineRun`、`ImportReport`、`MigrationReport`、`StoredArtifact`、`RunStatus` 在首次生产任务中定义，后续只消费这些接口。
- Original-site safety：Task 1 与 Task 9 使用哈希双重核对；共享脚本如需改动必须先加 V1 回归测试。
- Execution choice：受当前禁止分派代理约束，采用 `executing-plans` 同会话内执行，不创建子代理。
