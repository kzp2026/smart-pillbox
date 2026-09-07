"""Offline reproduction: python -m v2.research.reproduce experiment.json."""
import argparse
import json
from pathlib import Path
from v2.research.analysis import analyze
from v2.research.dataset import digest
from v2.research.evaluation import evaluate_predictions
from v2.research.provenance import source_snapshot
import hashlib


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment',type=Path)
    args=parser.parse_args()
    old=json.loads(args.experiment.read_text(encoding='utf-8'))
    sources={p:hashlib.sha256(data).hexdigest() for p,data in source_snapshot().items()}
    if digest(sources) != old['manifest']['source_sha256']:
        parser.error('算法源码摘要不一致；请从归档 source 目录运行原版本，而非当前工作区代码。')
    assert digest(old['dataset']['records']) == old['dataset']['card']['dataset_sha256'], '数据摘要不一致'
    analysis=analyze(old['dataset']['records'],**old['manifest']['config'])
    analysis['predictions'].extend(old.get('external_predictions',[]))
    evaluation=evaluate_predictions(old['gold'],analysis['predictions'],{r['comment_id'] for r in old['dataset']['records']})
    checks={name: analysis[name] == old['analysis'][name] for name in ('predictions','topics','mappings')}
    checks['metrics']=evaluation['metrics'] == old['evaluation']['metrics']
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == '__main__': main()
