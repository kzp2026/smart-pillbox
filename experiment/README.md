# 独立论文实验

唯一权威服务为 `experiment/pipeline/`，CLI 为 `run_experiment.py`。当前方法版本 `paper-repro-v2.1`。测试配置使用 `fake-design-v1`；正式配置显式使用严格真实文字provider，必须有费用授权；C组还必须有真实审核路径。图片不属于本轮批量实验。

```powershell
python experiment/run_experiment.py --config experiment/config.example.json --input data/京东智能药盒评论.csv
```

每次创建 `experiment/runs/<test或research>/<UTC时间_UUID>/`。命令打印目录及 `run_manifest.json`。旧 `output/` 只作 legacy 历史参考，不是本模块输入。

阶段顺序：clean → topics → requirements → mapping → graph → generation → evaluation → report。阶段失败立即停止，manifest 保存错误；不以模板补全失败。fake 是事先选择的模拟提供者，不是失败回退。

关键文件通过 `artifact(run, stage, filename)` 定位并校验哈希；禁止扫描“最新文件”。阶段产物在 `stages/<stage>/<attempt>/`，安全续跑新增 attempt，历史文件不被覆盖。

详见仓库根 `REPRODUCING.md`、`METHODS.md`、`DATA_CARD.md`、`EVALUATION.md`。本目录 `verification/` 在本地保存命令输出和验收记录；`verification/` 与 `runs/` 默认不进 Git，发布概况见 `docs/V2_RESEARCH_RELEASE.md`。`private/` 和阶段中的 `private/` 包含原始含昵称输入、组别对应表及 Prompt，仅限研究者私有保存。提供给评价者的包只包含 `blind_schemes.json` 与两份盲评表，禁止发送完整 run ZIP。
