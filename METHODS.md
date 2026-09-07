# 方法与证据边界

用户于2026-09-05选择C：保留两种方法，实验配置必须明确选择。没有“优先BERTopic、失败KMeans”的路径。锁定参数来自 `experiment/config.example.json`；实际算法、参数和模型文件摘要进入每个manifest。旧文件名中的BERTopic不能证明旧实验实际用了BERTopic。

KMeans＋TF-IDF：中文字符2–3 gram，max_features=3000，min_df=1，max_df=1.0，L2归一化，sublinear_tf=false；K=6，k-means++初始化（库默认并由源码版本固定），n_init=10，max_iter=300，tol=1e-4，Lloyd，seed=42，计算线程1。指定K大于独立特征向量数时失败，禁止自动减K冒称原参数实验。

BERTopic：本地 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，CPU，batch_size=32，归一化嵌入；UMAP n_neighbors=15、n_components=5、min_dist=0、cosine、random_state=42、transform_seed=42、n_jobs=1；HDBSCAN min_cluster_size=10、min_samples=5、euclidean、eom、prediction_data=true、core_dist_n_jobs=1；c-TF-IDF使用字符2–3 gram CountVectorizer、max_features=3000、min_df=1；top_n_words=10，nr_topics=null，不强制生成6个主题，保留-1离群标签。嵌入模型架构和截断长度由固定模型JSON锁定。依据：[BERTopic官方嵌入文档](https://maartengr.github.io/BERTopic/getting_started/embeddings/embeddings.html)、[模型官方版本记录](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/commits/main)。

主题编号只表示聚类结果。当前自动语义需求采用共享的版本化设计词典，针对每条评论可多标签命中；聚类只提供描述性的topic关联，不把人工规则伪称为主题模型自行理解。规则输出是候选，可能误判否定表达、过泛词和上下文，需独立标注。普通好评和无法可靠命名的文本归入needs_naming，不生成正式功能或结构。每条需求保存全部评论ID和证据片段，不能只给关键词摘要。

重要度：`I=0.5F+0.3N+0.2S`。F=该需求涉及的有效评论数/有效评论总数；N=包含负面词典指示的证据数/该需求证据数；S=至少15字的证据数/该需求证据数，作为明确标注的文本具体性代理。三者均在[0,1]，权重和1，原始计数、归一化分量与权重逐行保存。此排序不是需求真值、用户重要性量表或统计效果，需专家检验及敏感性分析。

需求是用户目标，功能是可执行行为，结构是实体/交互载体。两条映射理由分别保存。confidence默认null：未校准模型概率不能伪造成置信度。规则和设计推导不得自授approved；正式节点边只消费导入审核通过的关系。评论→需求→功能→结构路径在run文件中重建，生成只使用明确选择并记录的路径，每条映射最多选前三条证据进入Prompt。Neo4j可导入这些节点边展示，不参与无法复现的人工数据库检索状态。

A/B/C采用嵌套证据输入：A=基础设计任务＋统一通用约束；B=A＋规则辅助提取的需求候选和代表评论；C=B＋真实审核通过的需求—功能—结构路径。三组共享模型、请求参数、任务、输出栏目、max_tokens预算、图片数量0、重试策略，默认每组5次。通用工业设计约束三组相同；comment_specific_constraints独立记录，当前为空，不自动制造评论特定约束。B/C比较只估计加入审核映射路径的作用，不能证明图谱表示优于表格。输入长度与信息量并不相等，每组完整Prompt、字段差异和UTF-8长度公开给研究者，实际token用量以服务端usage为准。盲评者只接收匿名方案和量表，不能接收私有组别、输入和完整run包。

正式研究须使用config.research.json显式选择deepseek模型；测试使用config.example.json的fake，仅验流程。mode=research时无真实approved路径禁止整个含C批次发起请求，不借模拟审核；可先stop-after graph准备人工材料。真实接口复用v2/providers/text.py的严格方法，失败立即停止，无离线模板替代、无隐藏SDK重试；实际发送的消息和请求参数在调用前保存。DeepSeek文档未声明seed支持，因此实际请求不发送seed并记录unsupported_parameters；保存配置和源码不等于真实随机输出逐字复现。服务端无法确认的模型修订版和费用记unknown，响应模型、usage和耗时原样记录。依据：[DeepSeek官方Chat Completions参数](https://api-docs.deepseek.com/api/create-chat-completion/)。本轮未获得收费调用授权，接线验收采用明确标记的mock transport，不能称真实模型验收通过。

原始数据、算法结果、人工语义命名审核、设计推导、fake生成和专家评价是不同来源，JSON明确记录。旧自动打分只反映材料完整性，不能证明设计优秀、工程可行或已达标。


## 实际代码审计（方法版本 paper-repro-v2.1）

| 问题 | 代码证据 | 实际结论 |
|---|---|---|
| 10类从何而来 | `experiment/pipeline/semantics.py:10` 的 CATALOG | 预先编码的10组目标、触发词、功能、结构；当前数据只决定哪些规则命中，不自动发现新的类别 |
| 如何分配评论 | `semantics.py:27` matches 和 `:38` derive_requirements | 不区分词边界的子串命中，一条评论可以多标签；不是监督分类器或主题自动命名 |
| 聚类影响哪些字段 | `semantics.py:57` tids 与紧随的 topic_method | 只补充需求的topic_id、topic_method；cluster结果自身另输出簇编号/关键词/质量描述指标 |
| 去掉聚类后如何 | `tests/test_experiment_research_preparation.py` 的移除主题测试；`experiment/audit_methods.py` | 需求名称、归属、描述、关键词、频次、重要度、功能结构映射均不变；只能改变主题关联字段 |
| 情感如何计算 | `semantics.py:23`、`:24` 固定词典，derive_requirements逐条any命中 | 每条证据最多对正/负计数各贡献1；“不方便”会同时命中负面“不方便”和正面“方便”，两类不互斥；neutral为均未命中数，不是情感模型置信度 |
| 具体文本比例 | `semantics.py:56` | Python len(text)>=15的比例，包含标点、数字等字符；仅长度代理，不能解释为真正的语义具体性 |
| 权重如何确定 | config的importance及 `semantics.py:61` | 0.5/0.3/0.2为人为指定启发式，非数据学习或专家验证；加权和保留10位小数 |
| 功能结构从哪里来 | CATALOG与 `semantics.py:68` candidate_mappings | 固定设计规则提出候选；未做外部文献检索或模型推导，评论不直接证明选定器件合理；knowledge_source明确记录规则来源 |

正式论文应称“规则辅助需求归纳＋独立主题结构分析”。两种聚类的比较是评论分组比较，不是需求提取性能对比。规则曾参考当前整个评论集，当前集不能冒称未见测试集；需要冻结规则后新增独立数据，或将本案例限定为回顾性系统演示。

完整样例取数据C0001：原文涉及“语音、灯光、微信三重提醒”，命中reminder触发词，候选需求为REQ_reminder“清晰感知并确认服药提醒”；MAP_reminder→FUN_reminder“按计划发出多模态提醒并记录服药确认”→STR_reminder“扬声器、LED指示灯、时钟模块与确认按键”。原始证据支持提醒体验，功能和部件组合属于规则设计推导。当前review_status=pending_review，故该路径不能进入正式图谱或C组真实请求。人工真实审核通过后，路径连同C0001原文、两段理由和审核者进入run图谱及实际HTTP消息。完整评论、所有支持ID、实际分量值和移除主题对照由 `python experiment/audit_methods.py --run <run> --output <audit.json>` 导出，不能以示例省略的数据代替真实证据表。


本例实际统计：REQ_reminder有295/500条证据，F=0.59，N=0.06440677966101695，S=0.9389830508474576，I=0.5021186441。这是全体提醒证据的排序值，不是C0001单条评分。正负词同时命中可发生，实际计数见method_audit.json。
