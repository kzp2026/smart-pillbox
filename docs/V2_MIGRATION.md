# V2 独立知识库迁移手册

V2 使用 `agent_v2` 私有 schema、独立表结构和私有归档。迁移是“复制”，不会修改、删除或切换原站数据。

## 1. 初始化私有 schema

在目标 Supabase 项目的 SQL Editor 中执行：

`v2/migrations/001_agent_v2_schema.sql`

脚本会创建以下独立表：产品、评论批次、评论、需求、生成记录、流水线运行、阶段运行、归档文件、迁移台账和登录审计。所有表启用 RLS，并撤销 `anon`、`authenticated` 的直接权限；V2 仅通过服务端 PostgreSQL 连接访问。

## 2. 创建私有对象存储

在 Supabase Storage 中创建桶：

- 名称：`agent-v2-private`
- Public bucket：关闭
- 不创建匿名读取策略

V2 仅在服务端使用 `service_role` 密钥。密钥只放在新 Streamlit 应用的 Secrets 中，页面永不展示原值。若当前没有 Storage 服务密钥，可不配置这三项；V2 会把文件持久化到私有 `agent_v2.artifact_blobs` 表，功能和历史恢复能力保持完整，后续仍可切换到私有桶。

## 3. 准备登录密码哈希

在仓库根目录执行：

```powershell
python -c "from getpass import getpass; from v2.auth import hash_password; print(hash_password(getpass('Password: ')))"
```

把输出写入 `V2_PASSWORD_HASH`。不要把明文密码、真实 Secrets 或 `.streamlit/secrets.toml` 提交到 Git。

## 4. 配置迁移源

参考 `.streamlit/secrets.v2.example.toml` 配置：

- `V2_LEGACY_DATABASE_URL`：原站数据库，只读扫描 `public` schema，默认复制 `owner_id = private` 的数据。
- `V2_LEGACY_OUTPUT_ROOTS`：原站可见结果目录，使用分号分隔。
- `V2_DATABASE_URL`：V2 目标 PostgreSQL。
- `V2_SCHEMA = "agent_v2"`：目标私有 schema。

## 5. 执行迁移

登录 V2 后进入“设置与迁移”：

1. 点击“迁移预演”，确认源数据数量。
2. 勾选“确认仅复制数据，不更改原站”。
3. 点击“开始复制”。
4. 点击“哈希校验”。

迁移台账以源类型、源 ID 和文件 SHA-256 去重。重复执行会跳过已经复制的项目，不会制造重复评论、需求、生成记录或归档文件。

## 6. 验收标准

- 原网址仍能正常打开，原入口文件哈希未变化。
- V2 产品、评论、需求和历史生成记录数量不低于原站可迁移数量。
- 原站可见文件全部进入 V2 私有归档，SHA-256 校验一致。
- 未登录时不连接业务数据库；登录后只能看到 `V2_OWNER_ID` 对应数据。
- 删除产品只删除 V2 目标数据，不触碰原站。
