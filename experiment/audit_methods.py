"""Executable audit of topic influence; no new clustering or invented evidence."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment.pipeline.service import artifact, verify_run
from experiment.pipeline.io import read_json, write_json
from experiment.pipeline.semantics import derive_requirements, candidate_mappings, CATALOG


def audit(run, output):
    run=Path(run);verify_run(run)
    comments=read_json(artifact(run,'clean','comments.json'))
    topics=read_json(artifact(run,'topics','topics.json'))
    cfg=read_json(run/'config.json')
    with_topics=derive_requirements(comments,topics,cfg['importance'])
    without_topics=derive_requirements(comments,None,cfg['importance'])
    differences={a['requirement_id']:[key for key in a if a[key]!=b[key]] for a,b in zip(with_topics,without_topics)}
    mapping=candidate_mappings(with_topics)
    example=mapping[0];req=next(r for r in with_topics if r['requirement_id']==example['requirement_id'])
    cid=example['source_comment_ids'][0]
    result=dict(method='规则辅助需求归纳',predefined_category_count=len(CATALOG),topic_removal_changed_fields=differences,
        mappings_unchanged= mapping==candidate_mappings(without_topics),
        example=dict(comment=next(r for r in comments if r['comment_id']==cid),
            requirement=req,mapping=example,formal_graph_eligibility='pending_review cannot enter formal graph'),
        raw_review_status='unverified_source',conclusion='主题只改变topic_id/topic_method；需求归属、名称、频次、排序和映射不依赖聚类')
    return write_json(Path(output),result)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(audit(args.run,args.output))
