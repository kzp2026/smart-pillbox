# V2 验证与交付门

## Visual delivery quality gate
V2 generation tests must run through the `v2/app.py` entry path and verify that the shared design-package generator can be imported when the Python working path initially contains only the V2 entry directory.
- Unit tests must prove that a complete eight-asset plan receives `visual-delivery-v1` status `pass`, carries one canonical product identity, and contains per-asset acceptance criteria.
- Unit tests must prove that an incomplete plan receives `needs_revision` and lists its missing asset keys.
- The exploded prompt must contain a single assembly sequence and forbid duplicate shells/trays; the three-view must require orthographic same-scale views; the board must require CMF communication and prohibit illegible paragraphs; both usage prompts must require complete fingers.
- Run the no-cost plan gate before provider invocation. Do not substitute a provider call or a historical screenshot for this deterministic check.
- For a real provider acceptance, request an explicit paid-generation confirmation, then inspect the resulting pixels against the persisted criteria before describing them as final quality.

## 最小验证顺序

1. 运行新测试，确认 RED 失败原因是目标行为缺失。
2. 实现后重跑新测试和最接近的现有测试。
3. 运行 Skill 自测与项目契约校验。
4. 运行全部 V2 测试和仓库全量测试。
5. 对受影响用户旅程做 Streamlit AppTest 或真实浏览器检查。
6. 对 UI 改动做桌面/移动视觉对比。
7. 对数据改动做 dry-run、幂等、数量和哈希验证。
8. 重新检查原站冻结哈希与启动冒烟。

## 命令

在仓库根目录执行：

```powershell
python building-review-design-agent-v2/scripts/test_verify_contract.py
python building-review-design-agent-v2/scripts/verify_contract.py --repo-root .
python building-review-design-agent-v2/scripts/verify_contract.py --repo-root . --run-tests
python building-review-design-agent-v2/scripts/verify_contract.py --repo-root . --run-all-tests
python -m unittest discover -s tests -t . -p "test_*.py"
git diff --check
git status --short
```

定向原站与核心契约：

```powershell
python -m unittest tests.v2.test_original_freeze tests.v2.test_pipeline_catalog tests.v2.test_auth tests.v2.test_schema_sql
```

本地启动时关闭 Streamlit 开发模式，避免首次启动邮箱提示阻塞自动化：

```powershell
streamlit run v2/app.py --global.developmentMode=false --server.headless=true
streamlit run app.py --global.developmentMode=false --server.headless=true
```

## 按变更类型追加验证

| 变更 | 必须追加 |
|---|---|
| 登录/会话 | 未登录零业务查询、错误凭据、5 次锁定、冷却恢复、8 小时过期、退出 |
| 公开错误 | 数据库/第三方异常不回显主机、IP、连接串、账号、密钥或异常原文 |
| 数据/schema | 001→002 migration 前后兼容、12 表约束/索引/RLS、固定 owner、事务失败、重复执行 |
| 评论/需求 | 文件与评论指纹去重、可选评分/日期/版本/渠道/用户标签、证据归属、空结果、特殊字符 |
| 历史/资产 | 产品隔离、状态/模型/有图筛选、运行评审 upsert、两版本对比、证据追溯、按需文件加载、ZIP 下载、安全恢复时指定产品 |
| 文本/图片 provider | 无 Key、超时、有限重试、脱敏、离线标识、付费二次确认、幂等锁 |
| 提示词与历史评论隔离 | 新建文字与图像提示词仅保留评论编号、批次和排序信息，不含原始评论正文。设计、Prompt 与历史预览清除旧记录中的评论正文，并提供仅含提示词的下载。 |
| 导航/功能 | 10 个页面无异常、10 个旧阶段恰好映射一次、结果与效果图入口仍在 |
| 论文实验 | tests.v2.test_research_dataset / test_research_evaluation / test_research_service / test_research_ui：清洗守恒、稳定 ID、脱敏、无隐式算法替换、同一 test ID、公认手算指标、无训练泄漏、非法/重复/缺失输入拒绝、专家与用户分组、n<2 标准差为空、私有存档/哈希/重开/复现、无人工数据不声称准确率，桌面/手机界面检查 |
| 旧规则自检 | tests.test_evaluation_honesty、tests.test_ai_generation_outputs：空材料分数 0，四个旧列兼容且新增来源列，DOCX/优化提示不冒充专家结论 |
| 切页性能 | 页面切换 < 2 秒；切页重跑不重复初始化仓库；非概览页不额外读取全局快照；全局/产品计数各自单连接单查询；当前产品运行列表以 100 条共享缓存供各页切片使用；历史、图谱、设计方案与效果图首屏不读取归档/大文件；300 秒内快照、产品、运行与详情不重复加载；写入和退出后缓存失效；2 项运行时 WebP data URI 合计 < 900 KB 且只编码一次 |
| AI 效果图加载 | 切页先显示当前产品运行骨架，不 reopen 历史详情、不读取大图；点击“加载效果图预览”后只读取 `image/` 字节，离页清除预览标记以避免返回时自动重读；PostgreSQL 私有 blob 单连接批量读取，不逐图连接 |
| 产品历史隔离与草稿 | 新产品清除上一运行选择；页头显示当前产品；设计、Prompt、效果图和历史只显示当前产品；历史页明确提示其他产品默认隐藏，可主动选择查看；需求生成的产品名、需求、约束、供应商、模型和数量切页后保留，普通输入不改变当前产品 |
| Streamlit 热更新 | `v2/app.py` 不直接导入新增的 `WorkspaceSnapshot`；模拟上一版本缓存仓库缺少 `workspace_snapshot()` 时返回健康失败的零值快照而不崩溃；图像后台作业注册表使用 `getattr` 兼容旧运行时模块 |
| 百炼 Key 入口 | 侧栏醒目直达并说明只处理百炼效果图 Key、仅 `V2_IMAGE_API_KEY` 占位模板、当前 Key/DeepSeek Key 不回显、跳转 Streamlit 应用管理 |
| 付费生成 | 默认 8 张、0 张不调用图片服务、显式费用确认；完整套图包含产品效果图×2、爆炸图、细节图、三视图、展板、使用场景×2；逐图进度、部分成功持久化、失败可追溯，图片失败后文字方案和 Prompt 仍可打开 |
| 后台文字、图像与图谱 | `GenerationJobRegistry` 和 `ImageJobRegistry` 启动必须在 0.2 秒内返回且同一运行不重复启动；文字与图像调用均不占用 Streamlit 页面线程；无付费验收运行使用证据充分的输入，必须产出达标文字方案、Prompt、语义图谱和完整八图任务计划；图谱按需求去重并对每条需求保存具体功能、承载结构和用户证据；旧运行的通用模板图谱也必须重建为兼容的语义图谱；进程重启后的运行中任务只提示重新生成 |
| 初始化恢复 | 错误脱敏、不回退公共库、连接检查项、重试按钮和 Streamlit 应用管理入口可用 |
| UI/CSS/资产 | Chromium 1440×1000、390×844、无横向溢出/遮挡、无自定义机器人、应用 DOM 内无 Streamlit Viewer/状态/部署/页脚浮标、上传/下载/折叠面板标题/密码切换/代码复制无白底、hover/disabled/focus 可辨、控制台无错误 |
| 部署 | 新入口 `v2/app.py`、独立 Secrets、新网址、原网址与 Secrets 未变 |

## 数据迁移证据

论文实验还需验证：没有 gold 时非法预测仍被拒绝；同产品研究记录不挤掉设计历史；归档包含最小源码白名单，从归档 source 目录独立复现成功；报告 DOCX 可渲染，下载 ZIP 逐文件校验；无来源/标注/评分时的缺口与实际产物一致。`scripts/verify_paper_evidence.py` 可对指定既存输入建立独立本地验证目录（不连接生产服务），不补造人工输入。

真实迁移只有在用户已配置目标 Supabase 和 Secrets 后才能执行。交付证据至少包含：来源/目标表计数、可见文件数、总字节、重复 apply 新增数为 0、抽样或全量 SHA-256、一份可重新打开的历史运行，以及原站计数和文件未改变。

## 视觉证据

更新 UI 后覆盖 `docs/qa/` 中对应的正式截图，并在 `design-qa.md` 写明参考图、实现图、视口、状态、全屏对比、重点区域、发现、修复和最终结论。空数据库截图不能证明迁移成功；有数据状态必须用真实迁移夹具或已授权的私有环境另行验证。

## 完成标准

只有命令输出、浏览器行为、数据核验或云端状态有直接证据时，才能写“通过”“已迁移”或“已部署”。缺少凭据、云权限或真实数据时，明确标为待用户操作，不把本地模拟当成生产完成。

## paper-repro-v2.1 新验证门

新增tests.test_experiment_pipeline、test_experiment_integrity、test_experiment_legacy、test_experiment_evaluation及tests.v2.test_experiment_integration：清洗守恒510→500、真实算法名称、无回退、JSON复现、独立run、完整manifest和SHA256、源代码快照、审核证据校验、图谱路径进Prompt、盲组控制、真实/模拟区分、父审核继承、下游失效、安全续跑、V1V2字段修改及二次评价。

命令顺序不变：原站冻结 → Skill自测 → 静态契约 → --run-tests → --run-all-tests → tests全量发现 → git diff --check → git status --short。最后 python experiment/verify_e2e.py 执行独立新目录两方法与fake实验、模拟审核/二次评价；记录精确测试数量，不把模拟数据当专家结论。缺依赖须按experiment/requirements.lock.txt建立隔离环境，不跳过。收费接口和生产云服务只可待用户环境验证。

tests.test_experiment_final_guards 覆盖失败调用Prompt/参数/脱敏日志、标注规范预填、评论列默认识别及模型摘要变化拒绝续跑。E2E分别重复运行BERTopic和KMeans，逐阶段比较非AI JSON哈希。

test_research_ui 检查 legacy 表单前的正式入口指引；桌面/手机验证正式表单、运行状态、历史回评与修改入口可见。

tests.v2.test_experiment_ui 使用AppTest验证历史重开后立即显示状态和下载入口、更新当前产品，不只检查服务层返回值。

V2 集成测试还必须覆盖：相同 request_id 幂等返回、不同 request_id 创建新运行、research 准备在 graph 后暂停、paused/failed 归档可下载，以及 paper-repro-v2.0 历史只读兼容。UI 测试必须证明研究模式只提供“准备研究材料（停在图谱）”，不提供可误触的真实生成按钮，并显示真实 provider 仅作 CLI 配置说明。

Phase2门：tests.test_experiment_research_preparation / test_experiment_statistics_design / test_experiment_materials / test_experiment_source_snapshot；确认通用约束相同、移除主题只影响关联、正式provider身份与模型核对、无费用授权阻断、真实C审核阻断、请求体确含路径、缺失/不同评委设计阻断、独立初始标注不泄漏分类、补充材料哈希与新源码ZIP完整。python experiment/verify_preparation.py验证原始数据→准备→模拟审核→被拦截HTTP请求→SQLite持久化/重开/导出；真实模型、真人审核和生产云环境单列未验证。

tests.v2.test_research_release验证登录页公开方法版本及研究直接依赖声明。发布结果必须记录远端commit与云端版本/状态；仅有git push输出不能证明实际部署完成。
