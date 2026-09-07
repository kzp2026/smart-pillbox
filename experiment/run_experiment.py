"""Sole paper CLI. Real calls require explicit runtime spending authorization."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment.pipeline.service import STAGES,run_experiment,resume_experiment


def main():
    parser=argparse.ArgumentParser(description='可复现论文实验：独立目录、显式算法、fake A/B/C、人工证据门')
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--runs-root',type=Path)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--from-stage',choices=STAGES)
    parser.add_argument('--stop-after',choices=STAGES)
    parser.add_argument('--allow-paid-text-call',action='store_true',help='仅在用户明确授权费用后使用；授权本配置全部文字请求（含重试），不含图片')
    for option in ('mapping-review','reviews','changes','annotations','parent-run'):parser.add_argument('--'+option,type=Path)
    args=parser.parse_args();cfg=json.loads(args.config.read_text(encoding='utf-8-sig'))
    provider=None
    if args.allow_paid_text_call:
        if cfg['generation']['mode']!='research':parser.error('费用授权只可用于正式research模式')
        from experiment.pipeline.providers import configured_provider
        provider=configured_provider(cfg['generation'],allow_paid=True)
    if args.resume:
        if not args.from_stage:parser.error('--resume 必须指定 --from-stage')
        run=resume_experiment(args.resume,cfg,args.from_stage,stop_after=args.stop_after,provider=provider)
    else:
        if not args.input:parser.error('新运行必须指定 --input')
        run=run_experiment(cfg,args.input,args.runs_root,mapping_review=args.mapping_review,reviews=args.reviews,changes=args.changes,annotations=args.annotations,parent_run=args.parent_run,stop_after=args.stop_after,provider=provider)
    print(str(run.resolve()));print(str((run/'run_manifest.json').resolve()))


if __name__=='__main__':main()
