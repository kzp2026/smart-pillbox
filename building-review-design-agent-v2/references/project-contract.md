# Review Design Agent V2 项目契约

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
| 数据定义 | `v2/migrations/001_agent_v2_schema.sql` | `agent_v2`、11 张私有表、RLS、撤销公共角色 |
| 流程映射 | `v2/pipeline/catalog.py` | 10 个旧阶段完整映射到 7 个 V2 组 |
| V2 测试 | `tests/v2/` | 单元、集成、AppTest、冻结契约 |

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

V2 当前有 7 个真实阶段导航组：导入评论资产、需求生成、知识库概览、需求-功能-结构图谱、设计方案、工业设计 Prompt、AI 效果图；另有历史记录、设置与迁移，共 9 个导航页面。

底层必须继续覆盖 10 个旧研究阶段：评论清洗、关键词提取、情感分析、主题聚类、需求映射、Neo4j 图谱、AI 参数、设计方案、设计图片、方案评价。新增功能不得以删除旧阶段、旧文件兼容名、效果图槽位、历史打开、单文件下载、整包下载或安全恢复为代价。

## 身份与安全模型

- 只有一个私有用户；用户名和 scrypt 密码哈希来自 `V2_USERNAME`、`V2_PASSWORD_HASH`。
- 所有业务数据由服务器配置的 `V2_OWNER_ID` 隔离，页面不能改变 owner。
- 这是服务器端 PostgreSQL 连接模型，不使用 Supabase Auth 的 `auth.uid()` 多租户策略。
- 登录前不得创建业务仓库、查询产品或列出资产。
- 连续 5 次失败锁定 15 分钟；8 小时无操作退出。
- 数据库、Storage、DeepSeek、DashScope/OpenAI 密钥不得进入页面、日志、测试夹具或 Git。
- 页面公开错误只显示可操作的脱敏提示；数据库主机、IP、连接串、账号和异常原文不得回显。

## 数据与迁移模型

- `agent_v2` 是同一 Supabase 项目中的独立私有 schema；不复用原 `public` 表。
- 默认私有桶为 `agent-v2-private`；无 Storage 密钥时使用 `artifact_blobs`，不能回退到公共目录。
- 迁移只由登录用户显式触发：预演 → 确认仅复制 → 正式复制 → 数量/字节/哈希验证。
- 迁移台账使用来源标识和 SHA-256 保证重复执行不重复写入。
- 删除只作用于 V2；文件删除失败必须留下可重试状态。
- 每个运行使用独立 UUID 和资产路径；不能用共享固定文件名覆盖其他运行。

## UI 与视觉真值

- 参考图：`C:/Users/15854/AppData/Local/Temp/codex-clipboard-90f8cae9-bd85-4a4b-acb9-16ca5ac484a4.png`
- 当前桌面证据：`../docs/qa/v2-desktop-1440x1000.png`
- 当前移动证据：`../docs/qa/v2-mobile-390x844.png`
- QA 记录：`../design-qa.md`

视觉保持深海军蓝科技控制台、固定桌面侧栏、服务状态胶囊、七阶段流程、指标卡、操作卡、结果区和助手资产。桌面验收 1440×1000；移动验收 390×844，无页面级横向溢出、内容遮挡或不可读主操作。

## 变更权限边界

必须另行取得用户授权：修改原站数据结构、删除原站文件或历史数据、改变付费生成上限、增加新收费服务、切换 Supabase 项目、公开 Storage、改变单用户产品定位。
