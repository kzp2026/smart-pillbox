# Review Design Agent V2 项目契约

## Visual delivery quality gate
The V2 entry point must resolve the repository root before importing the shared design-package generator, so text/graph generation works when Streamlit starts from `v2/app.py` rather than the repository root.
- `v2/application/visual_quality.py` converts every new eight-image delivery plan into one canonical-product contract before any paid provider call.
- The contract adds asset-specific acceptance criteria to the two renders, engineering exploded view, detail, orthographic three-view, presentation board and two usage scenes.
- The gate must fail the plan when any required asset key is missing; it must not describe an incomplete or generic plan as passed.
- The prompt contract prohibits duplicate shells/trays, unexplained floating electronics, invented dimensions, unreadable pseudo-text and impossible hand-product intersections.
- The Design and Industrial Design Prompt pages expose the deterministic plan gate and acceptance criteria without reading image bytes.
- The gate validates the generation plan only. Provider pixels still require an owner review before they are accepted as final industrial-design artwork.

## 产品目标

在同一 Git 仓库保留原网页，同时维护一个独立的新入口、新网址、私有数据空间和单用户登录的 V2。V2 不是精简版；原站可运行、展示、恢复或下载的结果、效果图和功能都必须有对应入口。

## 当前权威入口

| 范围 | 权威路径 | 约束 |
|---|---|---|
| 原主站 | `app.py` | 冻结，不承载 V2 改动 |
| 原旧流程 | `app_legacy_current.py` | 冻结，保留旧研究流程 |
| 原页面 | `pages/` | 冻结，保留历史展示 |
| V2 入口 | `v2/app.py` | 第二个 Streamlit Cloud 应用入口 |
| V2 登录 | `v2/auth.py` | 单用户、scrypt、失败冷却、会话超时 |
| V2 配置 | `v2/config.py` | 只读服务器 Secrets，固定 owner |
| V2 数据 | `v2/adapters/postgres.py` | SQLite 测试适配 + PostgreSQL 私有 schema |
| V2 资产 | `v2/adapters/storage.py` | 私有 Supabase Storage 或数据库 blob |
| V2 迁移 | `v2/application/migration.py` | 只读来源、幂等复制、数量与哈希核验 |
| 数据定义 | `v2/migrations/001_agent_v2_schema.sql`、`002_product_workflow_hardening.sql` | `agent_v2`、12 张私有表、RLS、评论元数据和运行评审 |
| 流程映射 | `v2/pipeline/catalog.py` | 10 个旧阶段完整映射到 7 个 V2 组 |
| V2 测试 | `tests/v2/` | 单元、集成、AppTest、冻结契约 |
| 切页缓存 | `v2/application/view_cache.py` | 300 秒只读缓存，按私有仓库作用域失效；写入后立即清除 |
| 跨重跑状态 | `v2/application/runtime_state.py` | 仓库、存储、登录守卫、视图缓存、文字与图像后台作业跨 Streamlit 切页重跑复用 |
| 图像后台作业 | `v2/application/image_jobs.py` | 将百炼图片轮询移出页面请求线程，保存当前进度快照 |
| 文字后台作业 | `v2/application/generation_jobs.py` | 将文字方案、图谱与 Prompt 生成移出页面请求线程，再衔接图像作业 |

完整产品矩阵和架构以 `../docs/superpowers/specs/2026-07-16-review-design-agent-v2-design.md` 为准；迁移和部署分别以 `../docs/V2_MIGRATION.md`、`../docs/V2_DEPLOY_STREAMLIT_CLOUD.md` 为准。

## 原站冻结边界

`tests/v2/test_original_freeze.py` 保存并核对以下 Git blob SHA-1：

- `app.py`
- `app_legacy_current.py`
- `pages/01_现有流程备份.py`
- `pages/02_产品管理.py`
- `pages/03_旧版结果预览.py`

原站文件只有在用户明确要求改原站时才能改变。经授权变更后，先验证原站，再同步更新冻结测试和本契约；不得为了让测试通过而静默刷新哈希。

## 功能完整性

V2 当前有 7 个真实阶段导航组：导入评论资产、需求生成、知识库概览、需求-功能-结构图谱、设计方案、工业设计 Prompt、AI 效果图；另有论文实验中心、历史记录、设置与迁移，共 10 个导航页面。

## 论文实验中心（2026-09-04）

- `v2/ui/research.py` 提供独立正式入口；研究数据与设计结果不串用，设计历史/效果图不选择 provider=research 的运行。
- `v2/research/dataset.py` 生成来源卡、SHA-256、稳定评论 ID、列映射和排除日志。来源字段为 platform/product_ref/collection_method/collected_at/date_range/sampling/permission_note/anonymization_note。自动遮盖手机号/邮箱不等于完整匿名化。
- `v2/research/analysis.py` 运行中文字符 2–3 gram TF-IDF + KMeans、两种词典情感基线、可选 SnowNLP、全规则/首命中需求消融；显式记录实际方法、参数、依赖失败与有效主题数，不冒称 BERTopic。
- `v2/research/evaluation.py` 按最终仲裁真值的 test ID 计算 Accuracy、macro P/R/F1、micro F1 与情感混淆矩阵；拒绝未知/重复 ID、非法标签和缺失预测。多标签 Accuracy 为集合精确匹配。用户必须声明 test 未用于训练调参。
- 匿名专家/用户评分使用 1–5 整数量表、scheme_id、reviewer_id、role、dimension，拒绝重复评分；按方案/角色/维度汇总 mean 和样本 std（n<2 为 null）。关联方案保存原结果和证据快照。
- `v2/application/research.py` 复用现有私有运行/结果/资产表，provider=research、model=paper-evidence-v1，无新生产 migration 或 Secrets。归档为 paper-evidence.zip，含 DOCX、PNG、CSV、JSON、manifest.json 逐文件哈希、环境清单与空白人工模板。导入候选方法预测必须填写 method_notes，复现时仅重放这些预测而非调用外部模型。
- 实验历史、下载和再次复现均为显式操作。源上传不重复纳入论文归档，清洗样本是复现输入；没有人工证据时输出明确缺口，不生成专家高分或虚构准确率。
- `scripts/09_evaluate_design_scheme.py` 的兼容输出新增“来源”列，旧四列和文件名保留；分值只作材料完整性自检，空输入为 0，不作为论文实证评价。
- 新依赖 `matplotlib>=3.8.0`，沿用已部署的 python-docx 导出引擎。
- 归档 `source/` 保存最小可运行源码白名单及逐文件摘要，`reproduce` 验证源码和数据 SHA-256 后重算；不包含 Secrets、账号原列或其他私有配置。独立复现需进入归档 `source` 目录。论文归档不通过旧十阶段 ZIP 恢复入口执行源码。
- 仓库 `list_pipeline_runs` 支持 provider/exclude_provider 参数，SQL 先筛选再 LIMIT，研究与设计历史不会互相挤占列表。论文运行成功后更新当前产品上下文。
- 论文运行不计入全局/产品的设计生成完成计数，不能使设计方案和 Prompt 阶段被误标为完成；档案总数仍包含论文包。

底层必须继续覆盖 10 个旧研究阶段：评论清洗、关键词提取、情感分析、主题聚类、需求映射、Neo4j 图谱、AI 参数、设计方案、设计图片、方案评价。新增功能不得以删除旧阶段、旧文件兼容名、效果图槽位、历史打开、单文件下载、整包下载或安全恢复为代价。

## 身份与安全模型

- 只有一个私有用户；用户名和 scrypt 密码哈希来自 `V2_USERNAME`、`V2_PASSWORD_HASH`。
- 所有业务数据由服务器配置的 `V2_OWNER_ID` 隔离，页面不能改变 owner。
- 这是服务器端 PostgreSQL 连接模型，不使用 Supabase Auth 的 `auth.uid()` 多租户策略。
- 登录前不得创建业务仓库、查询产品或列出资产。
- 连续 5 次失败锁定 15 分钟；8 小时无操作退出。
- 数据库、Storage、DeepSeek、DashScope/OpenAI 密钥不得进入页面、日志、测试夹具或 Git。
- 页面公开错误只显示可操作的脱敏提示；数据库主机、IP、连接串、账号和异常原文不得回显。
- 侧栏提供醒目的“配置百炼效果图 Key”直达入口，并明确 DeepSeek 已独立配置、这里只处理阿里云百炼效果图 Key；设置页只展示 `V2_IMAGE_API_KEY` 占位模板并跳转 Streamlit 应用管理，不接收、不保存、不回显页面输入的 Key。DeepSeek 已有配置不要求重复填写。

## 切页性能模型

- 侧栏或移动端导航的目标交互预算为 2 秒以内。`v2/app.py` 每次控件交互都会重新执行，因此仓库、Storage、登录守卫、`ExpiringViewCache`、文字作业注册表和图像作业注册表必须定义在导入模块 `v2/application/runtime_state.py` 中，禁止在入口脚本内重新创建；数据库 schema 初始化每个进程/配置只执行一次。
- 运行时 WebP 的 base64 编码结果按进程缓存。AI 效果图页面先用当前产品的运行列表秒开骨架，并将已有图片归档的运行排在选择器前列，避免新的未完成运行遮蔽历史图片；不自动 reopen 历史详情或读取大图。只有用户点击“加载效果图预览”后才读取图片文件并显示预览，离开该页即清除预览标记，返回时不得自动重读大图；数据库私有 blob 使用单连接批量读取，禁止逐图片新建连接。图谱和设计方案首屏同样不读取归档文件字节，用户显式点击后才加载所选归档。
- 需求-功能-结构图谱从每次已保存的 `generation_runs.result_json` 直接显示，不依赖旧流水线额外产出图谱文件；快照必须按归一化需求去重，每条需求都映射到具体、可验证的功能和承载结构，并保留用户证据。旧运行缺失或仅有通用模板快照时，用已保存需求、约束和需求语义构造只读兼容图谱。
- 当前产品保存在会话上下文中。输入或创建新产品时清除上一产品的当前运行和图片预览状态；设计方案、Prompt、效果图与历史只查询当前产品。历史记录未删除，只有在用户主动选择其他产品时才显示该产品记录。需求生成页的产品名、需求、工业设计约束、供应商、模型和图片数量使用独立草稿状态；切换页面后必须恢复，普通输入不得改变当前产品。
- 工作台概览、流程状态、结果和证据均以 `v2_active_product` 为唯一上下文；切换产品使用真实 Streamlit 控件，不能使用不可点击的装饰卡代替操作。
- 历史页支持运行状态/模型/有图筛选、同产品两版本对比，以及按运行保存决策、0–5 分、备注和最终版本标记；历史首屏不自动读取归档大文件。
- 工作台页头必须显示当前产品、当前页面和百炼 Key 配置状态；历史页必须明确提示“当前仅显示某产品历史，其他产品默认隐藏”。
- Streamlit Cloud 热更新可能在短时间内重新执行新版 `v2/app.py`，同时保留上一版本的已导入模块。入口不得直接依赖本次新增的只读视图类型；工作台快照使用结构兼容的本地回退，遇到旧仓库对象时把健康状态降级为不可用、计数归零，但整站仍须进入登录或工作台。
- 同样地，入口读取图像后台作业注册表时必须通过 `getattr` 回退并补写到运行时模块，避免旧版 `runtime_state` 缓存缺少新属性时发生导入错误。
- 全局计数由 `workspace_snapshot()`、当前产品计数由 `product_workspace_snapshot()` 在一个数据库连接和一条聚合查询中返回，禁止导航栏按表逐次查询。
- 产品列表、运行列表、同一运行详情与工作台快照使用 300 秒进程内只读缓存；Key 使用数据库连接、owner 与 schema 的哈希作用域，不记录连接串明文。当前产品运行列表按 100 条共享缓存，不得因页面不同的展示条数重复查询。
- 导入、编辑、删除、流水线运行、文字/图片生成、归档恢复和迁移写入后必须立即清除当前私有作用域缓存；退出登录清除全部视图缓存。
- 缓存只减少 Streamlit 重跑和远程往返，不改变数据库、历史记录或资产的持久化真值。
- `v2/assets/*.png` 保留为视觉源文件；运行时只使用 `studio-background.webp`、`ai-brand-mark.webp`。两项 data URI 总载荷必须小于 900 KB；自定义机器人不再加载或渲染。

## 数据与迁移模型

- `agent_v2` 是同一 Supabase 项目中的独立私有 schema；不复用原 `public` 表。
- `run_reviews` 保存按 owner 隔离的运行决策；评论可选保存评分、评论日期、产品版本、渠道和用户标签，原评论文本始终保留。
- 默认私有桶为 `agent-v2-private`；无 Storage 密钥时使用 `artifact_blobs`，不能回退到公共目录。
- 迁移只由登录用户显式触发：预演 → 确认仅复制 → 正式复制 → 数量/字节/哈希验证。
- 迁移台账使用来源标识和 SHA-256 保证重复执行不重复写入。
- 删除只作用于 V2；文件删除失败必须留下可重试状态。
- 每个运行使用独立 UUID 和资产路径；不能用共享固定文件名覆盖其他运行。

## UI 与视觉真值

- 参考图：`C:/Users/15854/AppData/Local/Temp/codex-clipboard-90f8cae9-bd85-4a4b-acb9-16ca5ac484a4.png`
- 当前桌面证据：`../docs/qa/v2-desktop-1440x1000.png`
- 当前移动证据：`../docs/qa/v2-mobile-390x844.png`
- 上传控件证据：`../docs/qa/v2-import-controls-1440x1000.png`
- 百炼 Key 移动证据：`../docs/qa/v2-key-settings-390x844.png`
- QA 记录：`../design-qa.md`

视觉保持深海军蓝科技控制台、固定桌面侧栏、服务状态胶囊、七阶段流程、指标卡、真实操作入口和结果区。桌面验收 1440×1000；移动验收 390×844，无页面级横向溢出、内容遮挡或不可读主操作。主题隐藏可由应用 DOM 控制的 Streamlit Viewer、状态、部署和页脚浮标。

上传、下载、链接、表单提交、主次按钮、折叠面板标题、密码可见切换、代码复制和下拉选项必须使用同一深色控制台色板，包含高对比文字、hover、disabled 与 `:focus-visible` 状态；不得出现与页面冲突的白底按钮。

付费图片默认值为 8 张，0 张可只生成文字方案；完整套图固定覆盖产品效果图×2、产品爆炸图、产品细节图、产品三视图、设计展板和使用场景×2，且各图提示词必须有不同视角或任务。确认区必须显示最大付费调用数量并要求显式确认。创建运行后立即设为当前产品与当前运行；文字方案、Prompt 和每张图逐项持久化，单图失败不得丢失已成功图片或已保存文字结果。百炼调用必须进入进程内后台作业，页面立刻返回可切换状态并显示进度；服务进程重启后的未完成旧任务不得假装仍在执行，必须提示用户安全重新生成。

私有数据库初始化失败时不回退公共库，页面只显示脱敏检查项，并提供“重新连接私有服务”和 Streamlit 应用管理入口。

## 变更权限边界

必须另行取得用户授权：修改原站数据结构、删除原站文件或历史数据、改变付费生成上限、增加新收费服务、切换 Supabase 项目、公开 Storage、改变单用户产品定位。

## 权威论文实验服务（paper-repro-v2.1）

用户于2026-09-05选择两种算法显式配置。唯一服务 experiment/pipeline/，CLI experiment/run_experiment.py 和 scripts/run_paper_experiment.py、V2 application/experiment.py 共用。experiment/runs/<run_id>/ 创建独立目录，stages/<stage>/<attempt>不可覆盖，manifest记录全参数、源码/输入/输出/嵌入模型哈希、环境和完整Prompt；不得读output中的最新同名文件。BERTopic本地固定多语言模型和KMeans均无静默回退。

评论清洗510行审计保留500行，昵称仅在私有原始输入中，分析用匿名ID。semantics.py是共享需求命名与映射词典；规则输出pending_review或needs_naming，生成Prompt保存实际used_graph_paths。普通V2设计页可展示候选语义图谱，但明确无正式图谱证据；历史semantic-v2仅只读兼容。若研究者明确确认既有的限定关系清单，可将该清单作为“研究者确认关系证据”传入生成，必须保存映射编号、评论编号、审核意见与空白的待填审核人/日期，不得标注为专家验证或扩大到未确认关系。

新增v2/ui/experiment.py嵌入既有论文实验中心，不新增顶层导航、数据库表、Secrets、迁移。新运行使用 provider=research/model=paper-repro-v2.1，旧 paper-repro-v2.0 历史保持只读可打开；两者均通过现有私有表和 Storage 持久化。每次用户新建请求生成 request_id，同一 request_id 重复提交返回原运行，不同 request_id 即使配置相同也创建新运行。失败和停在 graph 的 paused 运行都保存完整 ZIP、状态与可下载历史；失败记录 FAILED，paused 映射为 PARTIAL。归档回评与修改经安全解包/哈希检查创建子运行，继承父审核关系，原运行只读。页面显示方法/算法/证据/审核关系/生成模式/独立评价/闭环。原paper-evidence-v1历史读取不混入新正式结果。

`experiment/config.example.json` 固定 mode=test/fake；`experiment/config.research.json` 固定 mode=research/DeepSeek。V2 网页允许明确查看真实 provider 选择，但正式研究按钮只执行到 graph，不调用文字模型，可导出人工审核材料。真实 A/B/C 生成仅从 CLI 传入已配置 provider 与显式本次付费授权；不得默认授权，也不得用 fake 输出冒充正式研究。

A/B/C使用同一显式provider、模型、参数、任务、通用约束、格式、图片0张和重试规则；A为基础任务，B加入需求与代表评论，C仅再加入真实审核路径。测试用fake，正式研究用严格DeepSeek请求，默认每组5次；盲表隐藏组和版本，私有对应表隔离。六类人工模板、评分严格校验、ICC、Wilcoxon、Holm、效应量与V1V2变更链由experiment/evaluation提供。无真实数据或模拟fixture禁止结论。旧quality_score兼容列新生成为0，页面称自动材料检查；不得冒称设计达标。

生成调用前写入 private/attempts 和 Prompt 文件，失败保留参数、重试次数和脱敏错误类型，停止下游；不生成替代方案。独立初次标注只提供原文，不展示规则答案；候选分类规范仅在初次标注封存后用于审核。V2上传默认识别评论内容列，避免将昵称列作为评论。

论文实验中心默认展开正式入口；其下原有辅助表单显式标记为 legacy 历史兼容工具，不与正式 run 混用。

正式运行、历史重开和评价/修改子运行成功后立即刷新，更新当前产品、七项状态及归档下载入口；无需额外点击其他控件。

补充契约：10类为预定义规则辅助需求归纳，聚类只影响topic_id/topic_method。正式C无真实approved即阻止请求。严格provider来自现有v2/providers/text.py，正式模式禁止mock客户端、核对请求模型；保存HTTP请求体但不含Authorization。SDK无隐藏重试，已尝试真实发送的批次禁止从generation及上游自动重发；失败/未知结果也计入尝试数。输入差异与长度透明导出。V2停在graph时归档review_materials并逐文件哈希，重新计算上游后旧补充材料标为历史。request_id绑定输入/配置/产品内容摘要，避免跨产品误复用。统计默认描述/探索，主要指标需求匹配度预指定，取消固定5对结论开关。源码ZIP包括未跟踪文件，排除密钥与历史数据。

发布核验：登录页仅显示公开METHOD_VERSION，不触发私有仓库初始化。根部署依赖显式包含jsonschema、scipy、threadpoolctl；精确研究环境仍以experiment锁文件为准。现有Streamlit应用更新不改变Secrets或schema；只发布审阅的源码/测试/文档，不发布本地run、验证日志或用户输出。
