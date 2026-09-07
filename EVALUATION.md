# 独立评价与V1—V2闭环

程序完整度检查仅回答是否有评论证据、审核关系、Prompt、参数和规定文件；没有方案质量分。旧“方案评价表.xlsx”是兼容自检文件，不是独立专家评价。真实研究必须采集下述数据，不能用程序规则/假模型替代。

## 六类模板与导入

本轮研究准备优先使用 `python scripts/prepare_review.py --run <run目录> --output <全新目录>` 导出的00—07表和填写说明。01_initial_free_annotation.xlsx是第一次独立标注，只含评论、自由问题/需求和无法判断选项，不展示系统类别；03_later_classification_review.xlsx在初次标注封存后使用。04_mapping_review.xlsx填写agree/modify/reject、真实匿名审核者、时间、知识来源和理由；05与07评分表另有逐维1—5分操作锚点。00来源核对、02老年场景候选核验、06修订链分别填写对应事实。未知项留空，不得把候选提示当成人工结论。

以下六类旧模板保留为兼容入口，其中带requirement_id的编码标注表用于后续分类审核，不能发给尚未完成初次独立标注的人员。

每个run的evaluation/templates目录生成：requirement_annotation.xlsx、annotation_guidelines.xlsx、expert_mapping.xlsx、abc_blind_review.xlsx、v1_changes.xlsx、v1_v2_blind_review.xlsx。

需求标注以原评论为单位，记录匿名annotator_id、时间、requirement_id和备注；没有明确诉求填NO_REQUIREMENT。同评论可由多名标注者独立标注，冲突应另由仲裁者决定，不能采用程序预测充当真值。映射审核表保留全部证据及两条关系理由，专家可修改语义名称、功能与结构说明，不能替换原证据或ID。自动候选默认pending_review，导入approved必须有匿名审核者和意见。approval只是审核记录，不代表工程可行性已经实测。

盲评仅提供匿名方案ID和方案内容，不含A/B/C及V1/V2版本；随机ID/展示顺序由系统安全随机数产生。私有对应表位于generation/private，不给评委。评委填写匿名ID、专业背景类别、七维原始1–5整数、优点、问题、建议、ISO时间。导入拒绝未知/重复方案、重复评委-方案、半填、缺失、非法评分、NaN/Inf及未匹配的修改链。完整ZIP含组别和原始数据，不能作为盲评包发送。

七维为需求匹配度、适老化友好性、功能完整性、操作便利性、结构合理性、工程可行性、创新性。量表原则：1=明显不满足且有严重缺口，2=多数不满足，3=部分满足且需重要修改，4=基本满足仅需小修，5=充分满足且有可核查依据；每个维度须由课题组在标注规范中增加领域锚点和例子。不得仅凭好看判定工程可行。

## 操作

以下三条使用config.example.json，仅演示fake测试闭环。正式数据改用config.research.json及真实审核材料；只有实际生成V2的命令需要已获授权者附加--allow-paid-text-call。导入评分不产生新的模型请求，不能为了导入评分重复生成整批方案。尚未获得密钥、费用授权和真实审核前，不执行真实生成。

```powershell
# 评分已有匿名方案，不重新生成新ID
python experiment/run_experiment.py --config experiment/config.example.json --input data/京东智能药盒评论.csv --parent-run <V1运行目录> --reviews <V1评分.xlsx>
# 修改表指定新的匿名V2 ID、低分<=3、原专家意见、相关需求/功能/结构、Prompt字段及真实改前/改后值
python experiment/run_experiment.py --config experiment/config.example.json --input data/京东智能药盒评论.csv --parent-run <已评分V1目录> --changes <修改记录.xlsx>
# 只导入V2新评分，旧评分从父运行冻结副本继承
python experiment/run_experiment.py --config experiment/config.example.json --input data/京东智能药盒评论.csv --parent-run <V2运行目录> --reviews <V2二次评分.xlsx>
```

可修改的文本Prompt字段为controls、functions、structure、layout、style、colors、typography、accessibility、content、negative_prompt，均要求改前值与V1实际Prompt完全一致。requirements为JSON列表，旧新值填写JSON并保留原需求ID及pending_review候选状态；不能伪造评论或审核状态。每个修改保存change_id、匿名评委、低分项、原意见、需求/功能/结构ID、字段旧新值和理由。V2实际替换Prompt并附上expert_changes，结果保留parent_scheme_id/change_ids及完整revision_chain。模型和参数保持一致，原运行只读；修改后的设计仍需二次验证，原已审图谱作为来源证据保留。

## 统计与局限

统计输出明确区分三种计数：`n_review_rows` 是评分行数，`n_unique_schemes` 是独立匿名方案数，`n_independent_pairs` 是至少有一名同一评委同时评价V1和V2的方案对数。多名评委评价同一方案只增加评分行，不能伪装成更多独立方案或方案对。

各方案/维度的n、均值、样本标准差、中位数和Student-t 95%区间以该方案的评委评分行为单位；n<2时区间和标准差为空。这些是对1–5有序量表的描述性近似，不证明方案总体质量，区间也不解决方案抽样、评委抽样、量表信效度或同一评委内相关性。完整交叉设计要求至少2名评委评价同一组至少2个方案；当前ICC(2,1)绝对一致性把每个“评委×方案”的七维均值作为单次综合评分，缺少任一交叉单元、评委或方案不足时返回`insufficient_complete_crossed_design`。ICC不适用于不同评委只评价各自方案的非交叉数据。

V1/V2必须由`pair_id`显式连接，且一个匿名方案不得跨方案对复用。每个方案对先取同时评价其V1和V2的同一评委，计算V2−V1，再在方案对内聚合；Wilcoxon的统计单位是独立方案对，而不是评分行或评委。无共同评委的方案对列入`incomplete_pair_ids`且不进入计算；两版评委集合不同的方案对列入`reviewer_set_mismatch_pair_ids`。确认性设计默认要求两版评委集合完全一致，不能仅靠交集静默丢弃评分；若研究另有缺失数据方案，应在看结果前另行规定和论证，当前实现不替代该方案。

默认调用只做描述和探索性计算，即使有5个或更多方案对也不会自动允许显著性结论。为兼容已有模拟计算，默认返回的p值不会删除，但总结果和每个维度都以`p_value_role="exploratory_only"`明确标识，且`significant=false`。需要推断时必须显式传入`design`，声明：主要指标、在查看结果前预指定、独立方案对为分析单位、同评委配对、双侧检验、完整方案对处理、相同评委集合、独立方案对假设、差值分布对称假设，以及不由观察结果倒推的样本量依据。当前准备阶段预指定的唯一主要指标是“需求匹配度”，这属于研究准备记录，并非公开注册或时间戳预注册；其余六项是次要/探索性指标。设计满足时，只有主要指标标为`confirmatory_primary`，其他维度仍标为`exploratory_secondary`。

Wilcoxon使用双侧检验，`zero_method="wilcox"`剔除零差值，并列绝对差使用平均秩；匹配秩二列效应量以非零差的正负秩和计算。SciPy说明该检验针对配对差值分布关于零对称的原假设，并假设差值观测独立同分布；有并列或零值时所谓exact p值不再严格精确，`method="auto"`会按数据情况选择方法。因此p值必须连同实际方案对数、零差数、缺失和假设状态报告，不能把一个固定样本量阈值当作适用性证明。七维Holm校正值保留用于探索性多指标查看；唯一预指定主要指标按其原始双侧p值与α=.05判断，次要指标不会被程序标成确认性显著。实现依据[Scipy Wilcoxon官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html)与[Scipy Student-t官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html)。

`can_claim_significance`只有在显式设计完整、数据非模拟、没有不完整方案对或评委集合不一致，且主要指标达到预定α时才可能为真；它仅表示该预指定检验的统计判定可报告。`can_claim_real_improvement`始终为false，程序永不自动声称“真实改善”“质量提高”或工程有效。统计显著也不能替代效应大小、置信区间、实际重要性、专家判断、可用性实验或工程原型验证。

A/B/C私有表支持将盲评汇总按组分析；当前各方案七维描述与评委一致性可直接导出。真实模型、真实专家评价、用户可用性实验和工程原型验证均待课题组提供，不得从fake运行推断设计有效。
