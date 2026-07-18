# V2 验证与交付门

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
| 数据/schema | migration 前后兼容、约束/索引/RLS、固定 owner、事务失败、重复执行 |
| 评论/需求 | 文件与评论指纹去重、组合筛选、分页排序、空结果、特殊字符 |
| 历史/资产 | 刷新后恢复、单文件/ZIP 下载、SHA-256、删除失败可重试、安全解压 |
| 文本/图片 provider | 无 Key、超时、有限重试、脱敏、离线标识、付费二次确认、幂等锁 |
| 导航/功能 | 9 个页面无异常、10 个旧阶段恰好映射一次、结果与效果图入口仍在 |
| UI/CSS/资产 | Chromium 1440×1000、390×844、无横向溢出/遮挡、键盘焦点、控制台无错误 |
| 部署 | 新入口 `v2/app.py`、独立 Secrets、新网址、原网址与 Secrets 未变 |

## 数据迁移证据

真实迁移只有在用户已配置目标 Supabase 和 Secrets 后才能执行。交付证据至少包含：来源/目标表计数、可见文件数、总字节、重复 apply 新增数为 0、抽样或全量 SHA-256、一份可重新打开的历史运行，以及原站计数和文件未改变。

## 视觉证据

更新 UI 后覆盖 `docs/qa/` 中对应的正式截图，并在 `design-qa.md` 写明参考图、实现图、视口、状态、全屏对比、重点区域、发现、修复和最终结论。空数据库截图不能证明迁移成功；有数据状态必须用真实迁移夹具或已授权的私有环境另行验证。

## 完成标准

只有命令输出、浏览器行为、数据核验或云端状态有直接证据时，才能写“通过”“已迁移”或“已部署”。缺少凭据、云权限或真实数据时，明确标为待用户操作，不把本地模拟当成生产完成。
