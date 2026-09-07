# 人工标注与审核材料

使用独立命令从任一已产生 `comments.json` 的实验运行导出材料；无需等待 graph 或 generation 完成：

```powershell
.venv-research\Scripts\python.exe scripts\prepare_review.py --run <实验运行目录> --output <材料目录>
```

材料按顺序使用：先核对数据来源，再封存独立初始自由标注；之后才向另一份表加入系统需求候选并开展分类审核。初始表只显示 `comment_id`、评论原文、使用问题、自由需求描述、无法判断和标注者信息，不展示系统分类答案。历史 `requirement_annotation.xlsx` coded 表仍可由 `import_annotations` 导入，但应在论文中说明其并非本轮独立自由标注。

适老场景表中的“明确文本支持 / 一般 / 未知”是基于原文字词的候选提示，只用于抽样和排期，不是人工结论。mapping 表须审核需求、功能、结构、证据、两段关系理由和 `knowledge_source`；`review_decision=agree/modify/reject` 与匿名审核者、时间和意见必须由真实人员填写。导入前用 `import_mapping_reviews` 转换：agree→`review_status=approved`，reject→`review_status=rejected`，modify→`review_status=pending_review` 并根据意见新建候选。输出继续包含 graph 接口使用的 `review_status`、`reviewer_id`、`reviewer_note`；不能篡改原映射身份或证据。

七维评分均使用 1–5 分及表内可操作锚点。盲评表不得增加方案版本或方法身份。V1→V2 修改记录与后续盲评分开保存。不得预填、伪造人员评分或批准。

数据来源核对表包括平台、产品标识、采集时间、评论时间范围、采集方式、筛选规则和来源凭据；未知项留空。`materials_manifest.json` 列出尚缺材料和可复制的导入命令。

规则开发边界见 `BOUNDARY_DISCLOSURE.md`：rules 已查看全部数据时，该数据不能被称为独立验证；只有冻结规则后使用未参与开发的新数据，才可报告独立验证。
