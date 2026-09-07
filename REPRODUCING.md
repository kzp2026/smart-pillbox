# 复现实验

原站仍为 `streamlit run app.py`；V2 为 `streamlit run v2/app.py`。正式论文入口为 `python experiment/run_experiment.py`，旧命令行的对应入口为 `python scripts/run_paper_experiment.py`，两者调用同一服务。`output/` 中旧文件原样保留且均属 legacy；旧文件不能用作本次自动重跑的权威结果。

## 环境

本次验收使用 Windows、Python 3.12。完整精确版本见 `experiment/requirements.lock.txt`，基础 KMeans 环境见 `experiment/requirements-base.lock.txt`，每次 manifest 另外记录全部已安装发行包。不要混用全局 Python 或 `.test_deps`。在 D 盘创建隔离环境：

```powershell
python -m venv .venv-research
$env:PIP_CACHE_DIR="$PWD/.research-cache/pip"
.venv-research/Scripts/python -m pip install -r experiment/requirements.lock.txt
$env:PATH="$PWD/.venv-research/Scripts;$env:PATH"
$env:PYTHONUTF8="1"
$env:MPLCONFIGDIR="$PWD/.research-cache/matplotlib"
$env:NUMBA_CACHE_DIR="$PWD/.research-cache/numba"
```

BERTopic 必须准备指定中文可用的多语言嵌入模型。`python experiment/download_model.py` 从官方 Hugging Face 仓库下载固定 revision，只下载公开模型、无需 Key；缓存位于 D 盘工作区 `.research-cache/`。固定模型 ID、revision 和逐文件 SHA-256 见 `experiment/models/embedding_manifest.json`。算法运行仅加载本地文件并验证锁定摘要；缺失模型直接失败，不自动联网取替代模型，不切换 KMeans。

## 从新目录运行

```powershell
python experiment/run_experiment.py --config experiment/config.example.json --input data/京东智能药盒评论.csv --runs-root experiment/runs/new-study
python experiment/compare_methods.py --config experiment/config.example.json --input data/京东智能药盒评论.csv --runs-root experiment/runs/method-comparison
```

第一条明确 KMeans＋TF-IDF，默认 A/B/C 各5次，fake，图片数统一0。第二条顺序运行 KMeans＋TF-IDF 和 BERTopic，任一失败即退出并保留其失败 manifest，不用另一方法替代。比较文件引用两个独立 run ID；silhouette 的表示空间不同，不能直接作为优劣排名。

每个 run 的 config、输入副本、源码快照、阶段文件哈希、模型参数、完整 Prompt、原始响应、错误和最终列表都在 `run_manifest.json`。JSON 是机器复现真值；Excel 是人工阅读/编辑投影，工作簿容器时间戳不作为算法随机性判断。相同固定环境和模型下，非 AI 阶段 JSON 的内容和 SHA-256 应相同。匿名方案 ID、UTC 时间、run ID 和 Excel 容器元数据有意不同。

## 审核、续跑与历史

正式研究先准备到图谱：

```powershell
python experiment/run_experiment.py --config experiment/config.research.json --input data/京东智能药盒评论.csv --stop-after graph
python scripts/prepare_review.py --run <上条打印的run目录> --output <全新人工材料目录>
```

当前没有真实审核路径，含C组的正式生成会直接失败，不能当作完整C组。初次独立标注只发01表；系统候选分类与映射材料应在独立标注封存后交给相应审核人员。04映射表填写agree/modify/reject、匿名审核者、ISO时间、理由和知识来源，导入前不要自行把自动候选标成已审核。

```powershell
python experiment/run_experiment.py --config experiment/config.research.json --input data/京东智能药盒评论.csv --annotations <已填写01表.xlsx> --mapping-review <已审核04表.xlsx> --stop-after graph
```

正式文字生成复用已有安全配置V2_DEEPSEEK_API_KEY/V2_DEEPSEEK_BASE_URL；模型名由config.research.json显式固定，不能由Secrets悄悄覆盖。当前本地没有检测到可用V2文字Key，也未获得本轮收费授权，以下命令只能在这两项准备好之后由获授权者执行：

```powershell
python experiment/run_experiment.py --config experiment/config.live-smoke.json --input data/京东智能药盒评论.csv --allow-paid-text-call
# 最小真实调用通过后，才执行同模型、同预算的正式批次：
python experiment/run_experiment.py --config experiment/config.research.json --input data/京东智能药盒评论.csv --mapping-review <真实审核04表.xlsx> --allow-paid-text-call
```

默认批次A/B/C各5次；调用上限为组数×次数×(1+max_retries)。费用数额和精确模型修订版本未由接口证实时记unknown。本轮未调用这些命令。真实seed不承诺受支持；实际发送参数和完整HTTP JSON保存于每条记录actual_request，Authorization不保存。出现真实调用后，禁止从generation或更早阶段自动重发整批；只允许从evaluation/report续跑，重做生成须新建显式实验并重新核对费用范围。

无偿软件验收的模拟审核必须 `simulated=true`、评委ID以SIM开头、文件注明fixture，与真实实验分开。模拟审核永远不能作为专家结论。

可先 `--stop-after mapping`，再 `--resume <run目录> --from-stage graph`。续跑必须相同完整配置、源码、输入和上游哈希，旧 attempt 只读保留；不允许手改已登记的上游结果。要导入新的人工资料或升级代码，创建新运行；回评/修改用 `--parent-run`，不改旧记录。

V2“论文实验中心 → 正式复现实验”调用相同核心，并私有保存完整归档；新正式运行与旧 paper-evidence-v1 记录分开加载。回评入口校验归档路径和逐文件哈希后创建子运行。生产数据库、Storage、登录和收费图片接口本次未触碰；云端权限需在用户环境另行验证。

## 验证

执行用户要求的八条命令，本轮完整结果见 `experiment/verification/phase2/final-confirmed/`，本轮交付索引见 `experiment/verification/phase2/DELIVERY.md`。上一轮 `experiment/verification/DELIVERY.md` 原样保留。`python experiment/verify_e2e.py` 建立全新验收目录，检查510→500审计、非AI复现、候选命名、真实图谱空状态、模拟审核路径、fake A/B/C及模拟V1—V2闭环，产出 `acceptance.json`。该验收脚本历史命名的formal子目录及formal_run字段仍属于mode=test的fake基线，绝非真实正式对照实验；以manifest中的experiment_mode与generation_mode为准。模拟评分只验证统计代码，不能写入论文结果。


## 本轮准备验收与源码固定

`python experiment/verify_preparation.py` 使用原始510条案例数据，先验证research C无审核阻断与最小调用费用门，再在明确transport_test模式拦截urllib HTTP请求，核对实际请求体、15条生成记录、30条C路径、SQLite历史重开、ZIP导出与重复提交。HTTP响应和审核均为SIM fixture，绝非真实AI或人工评价。

`python experiment/source_snapshot.py --repo-root . --output <新源码交付目录>` 打包已跟踪及未跟踪源码、文档、测试和应用资产，逐文件SHA及ZIP SHA写入source_manifest.json；排除Secrets、数据、历史和依赖缓存。旧commit＋dirty标识不能替代这个快照。

inference_design在配置中于生成前保存并哈希；默认inference_requested=false，主要指标预指定为需求匹配度，其余为探索性。查看真实结果后不得通过改配置或续跑冒充事前指定；需要改变方法时另存版本并披露。
