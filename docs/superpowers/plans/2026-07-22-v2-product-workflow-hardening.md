# V2 Product Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 V2 当前产品串线、付费生成风险、结果无法决策、初始化恢复不清楚和右下角浮标问题。

**Architecture:** 在现有 domain/application/adapter/UI 分层内做增量扩展；用编号 migration 保存评论元数据和运行评审，用产品级聚合查询驱动导航状态，用 Streamlit 原生控件承载真实操作。保持单用户私有数据模型和 30 秒只读缓存。

**Tech Stack:** Python 3、Streamlit、SQLite/PostgreSQL、Supabase、unittest。

## Global Constraints

- 不修改 `app.py`、`app_legacy_current.py` 和 `pages/`。
- 不回退到公共数据库或公共存储。
- 付费图片默认 1 张且必须显式确认。
- 所有结果和历史严格按当前产品过滤。
- 所有凭据只来自 Streamlit Secrets。

---

### Task 1: 回归测试和产品级上下文

**Files:** `tests/v2/test_app_structure.py`, `tests/v2/test_repository.py`, `v2/domain/models.py`, `v2/adapters/postgres.py`, `v2/app.py`

- [ ] 写概览过滤、产品级快照、真实操作入口和默认图片数的失败测试。
- [ ] 运行目标测试并确认因行为缺失失败。
- [ ] 实现产品级快照、当前产品选择、可点击入口和默认 1 张。
- [ ] 运行目标测试确认通过。

### Task 2: 运行评审、对比和证据链

**Files:** `v2/migrations/002_product_workflow_hardening.sql`, `v2/domain/models.py`, `v2/adapters/postgres.py`, `v2/application/history.py`, `v2/app.py`, `tests/v2/test_repository.py`, `tests/v2/test_history.py`, `tests/v2/test_schema_sql.py`

- [ ] 写运行评审 owner 隔离、覆盖更新、证据列表和 migration 的失败测试。
- [ ] 运行目标测试确认失败。
- [ ] 实现评审持久化、历史筛选、双运行对比和证据展示。
- [ ] 运行目标测试确认通过。

### Task 3: 生成安全和进度

**Files:** `v2/application/image_generation.py`, `v2/app.py`, `tests/v2/test_image_generation_service.py`, `tests/v2/test_app_structure.py`

- [ ] 写逐图进度回调、费用文案和部分成果保留测试。
- [ ] 运行目标测试确认失败。
- [ ] 实现进度回调、阶段状态、1 张默认值和可重试失败提示。
- [ ] 运行目标测试确认通过。

### Task 4: 初始化恢复、导航分组和浮标清理

**Files:** `v2/app.py`, `v2/ui/components.py`, `v2/ui/theme.py`, `tests/v2/test_app_structure.py`, `tests/v2/test_components.py`, `tests/v2/test_theme.py`

- [ ] 写服务恢复页、无机器人、Streamlit 浮标隐藏和设置分组测试。
- [ ] 运行目标测试确认失败。
- [ ] 实现脱敏诊断、重试、管理入口、导航说明、归档产品选择和浮标 CSS。
- [ ] 运行目标测试确认通过。

### Task 5: Skill 同步和完整验证

**Files:** `building-review-design-agent-v2/references/project-contract.md`, `building-review-design-agent-v2/references/workflow.md`, `building-review-design-agent-v2/references/verification.md`, `building-review-design-agent-v2/scripts/verify_contract.py`, `design-qa.md`

- [ ] 同步当前功能真值、流程和验证门。
- [ ] 运行原站冻结、目标测试、全量测试和契约验证。
- [ ] 运行 `git diff --check` 并记录线上无法由代码修复的 Secrets 状态。
