# V2 Streamlit Cloud 新入口部署

目标是同一 GitHub 仓库、两个 Streamlit 应用、两个网址：

- 原应用入口保持现状，例如 `app.py`。
- 新应用入口使用 `v2/app.py`。

## 部署前

1. 按 `docs/V2_MIGRATION.md` 初始化 `agent_v2` schema 和私有 Storage 桶。
2. 生成登录密码哈希。
3. 复制 `.streamlit/secrets.v2.example.toml` 的字段到新应用 Secrets，并替换占位值。
4. 不修改原应用的入口、Secrets 或网址。

### PostgreSQL 连接地址

- V2 与原站使用同一个 Supabase 项目时，优先把原应用中已经验证可用的 `PRODUCT_KB_DATABASE_URL` 或 `DATABASE_URL` 的值复制为新应用的 `V2_DATABASE_URL`；数据隔离由 `V2_SCHEMA = "agent_v2"` 保证。
- 使用 Supabase Shared Transaction Pooler 时，必须从项目顶部 **Connect** 面板完整复制 URI。用户名形如 `postgres.<project-ref>`，端口为 `6543`，密码是 Supabase 数据库密码，不是 V2 登录密码。
- 不要因为单个新应用连接失败就重置数据库密码。确需重置时，必须同步更新所有使用该数据库的应用，否则原站会失去连接。
- 保存 Secrets 后等待应用重启，再登录并核对“数据库：PostgreSQL 私有 schema”、产品数、评论数和需求证据数。认证失败时页面只能显示脱敏提示，不得回显连接异常原文。

## 新建应用

在 Streamlit Community Cloud 中选择同一仓库和同一分支，创建第二个应用：

- Main file path：`v2/app.py`
- Python：与原应用相同的受支持版本
- App URL：选择新的唯一 slug，例如 `review-design-agent-v2-kzp2026`

部署后先不要执行迁移。依次验收：

1. 未登录只能看到私有登录页。
2. 连续输错 5 次会锁定 15 分钟。
3. 登录后 9 个导航页面都能打开。
4. “设置与迁移”中的数据库连接检查通过。
5. 迁移预演、复制、哈希校验全部通过。
6. 导入一份测试评论，生成文字方案；图片数量为 0 时不得调用付费图像接口。
7. 选择图片数量后，确认页必须准确显示供应商、模型和数量，只有二次确认后才能调用。
8. 历史记录可重新打开、单文件下载、整包下载；ZIP 恢复会先进行安全检查。
9. 再次访问原网址，确认功能和历史展示均未改变。

## 回滚

V2 与原站入口、schema、Storage 桶均独立。出现问题时只需暂停或删除新的 Streamlit 应用；不要删除 `agent_v2` schema 或私有桶，待导出数据并确认后再处理。原应用不需要回滚。
