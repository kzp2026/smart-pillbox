# Review Design Agent 项目协作规则

本文件适用于整个仓库，并补充用户级全局规则。

## 原站保护

- `app.py`、`app_legacy_current.py` 和 `pages/` 是原站边界。除非用户明确要求修改原站，否则不得改变。
- 开始和结束 V2 工作都运行 `python -m unittest tests.v2.test_original_freeze`。
- 不得覆盖或清理与当前任务无关的用户改动、未跟踪截图或浏览器产物。

## V2 工作必须使用并同步 Skill

<!-- skill-sync:building-review-design-agent-v2 -->

- 任何涉及 `v2/`、`tests/v2/`、V2 migration、`.streamlit` 中 V2 配置、`docs/V2_*`、`design-qa.md` 或 V2 部署的任务，先完整读取 `building-review-design-agent-v2/SKILL.md` 及其要求的 references。
- 新增、删除、重命名或改变 V2 的页面、功能、字段、表、provider、环境变量、导航、产物、测试门或部署步骤时，必须在同一任务同步更新 `building-review-design-agent-v2/`，不能留到以后。
- 更新位置遵循 Skill 的 “Keep This Skill Synchronized”：当前真值写入 `references/project-contract.md`，流程写入 `references/workflow.md`，验证门写入 `references/verification.md`，可自动检查的契约写入 `scripts/verify_contract.py`。
- 完成前运行：

```powershell
python building-review-design-agent-v2/scripts/test_verify_contract.py
python building-review-design-agent-v2/scripts/verify_contract.py --repo-root . --run-all-tests
```

- 如果改动只是内部重构且 Skill 无需修改，交付说明必须写明未改变任何外部行为、路径、约束或验证命令，并仍运行契约校验。
