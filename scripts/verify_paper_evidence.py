"""Run existing comments through the private paper workflow without invented human labels."""
import argparse
import json
import io
import zipfile
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from scripts.upload_parsing import default_comment_column, read_upload_table
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.artifacts import ArchiveLimits, extract_archive
from v2.application.research import ResearchService
from v2.research.dataset import prepare_dataset


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',default='智能药盒 · 来源待核验样本')
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('输出目录必须为空，避免覆盖已有验证证据。')
    args.output.mkdir(parents=True,exist_ok=True)
    data=args.input.read_bytes()
    frame=read_upload_table(args.input.name,data)
    columns={'comment':default_comment_column(frame)}
    for target,aliases in {'rating':('评分','rating'),'date':('日期','时间','date'),'variant':('产品','规格','variant'),'channel':('渠道','平台','channel')}.items():
        match=next((a for a in aliases if a in frame.columns),None)
        if match: columns[target]=match
    dataset=prepare_dataset(frame,data,args.input.name,columns,{
        'collection_method':'仓库既存输入用于功能验证；采集方式未核验',
        'anonymization_note':'软件自动遮盖手机号/邮箱；尚未人工复核，不作公开论文数据。'})
    repo=KnowledgeRepository(f'sqlite:///{args.output.resolve() / "validation.sqlite3"}','local-verification')
    repo.initialize()
    service=ResearchService(repo,LocalArtifactStore(args.output/'private-artifacts'))
    result=service.run(args.product,dataset,dict(seed=42,n_topics=6,use_snownlp=True))
    archive=service.download(result['manifest']['run_id'])
    (args.output/'paper-evidence.zip').write_bytes(archive)
    evidence=(args.output/'evidence').resolve()
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
        for name in bundle.namelist():
            destination=(evidence/name).resolve()
            if evidence not in destination.parents: raise ValueError('生成归档存在非法路径')
            content=bundle.read(name)
            if name!='manifest.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][name]:
                raise ValueError('生成归档哈希不一致')
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(content)
    replay=service.replay(result['manifest']['run_id'])
    checks={k:result['analysis'][k]==replay['analysis'][k] for k in ('predictions','topics','mappings')}
    checks['no_fabricated_metrics']=not result['evaluation']['metrics']
    checks['no_fabricated_reviews']=not result['review_summary']
    summary={'input_rows':len(frame),'counts':dataset['card']['counts'],'actual_methods':result['analysis']['methods'],
             'evidence_coverage':result['analysis']['evidence_coverage'],'checks':checks,'readiness':result['readiness'],
             'run_id':result['manifest']['run_id'],'replay_run_id':replay['manifest']['run_id']}
    (args.output/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__=='__main__': main()
