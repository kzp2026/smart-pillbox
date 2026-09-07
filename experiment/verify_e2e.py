"""No-cost acceptance on bundled comments. Synthetic reviewers are explicitly fixtures."""
from __future__ import annotations
import argparse
import copy
import json
import sys
import uuid
import zipfile
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from experiment.pipeline.service import run_experiment,artifact,verify_run
from experiment.pipeline.io import read_json,write_json,sha256
from experiment.pipeline.graph import reconstruct
from experiment.evaluation.statistics import DIMENSIONS

REPO=Path(__file__).resolve().parents[1]


def check(condition,message):
    if not condition:raise AssertionError(message)


def data(run,stage,name):return read_json(artifact(run,stage,name))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runs-root',type=Path,default=REPO/'experiment/runs');args=parser.parse_args()
    root=args.runs_root/('acceptance_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);root.mkdir(parents=True,exist_ok=False)
    cfg=read_json(REPO/'experiment/config.example.json');source=REPO/'data/京东智能药盒评论.csv'
    formal=run_experiment(cfg,source,root/'formal');replica=run_experiment(cfg,source,root/'replica')
    a,b=verify_run(formal),verify_run(replica)
    check(a['counts']==dict(raw=510,valid=500,empty=0,duplicate=10,too_short=0,removed=0,merged=10),'清洗守恒失败')
    check(len(data(formal,'clean','cleaning_audit.json'))==510,'清洗审计不完整')
    compared=[]
    for stage in ('clean','topics','requirements','mapping','graph'):
        ah={Path(p).name:h for p,h in a['stages'][stage]['outputs'].items() if p.endswith('.json')}
        bh={Path(p).name:h for p,h in b['stages'][stage]['outputs'].items() if p.endswith('.json')}
        check(ah==bh,'非AI结果不重复：'+stage);compared.append(stage)
    check(not a['fallback_occurred'] and a['actual_algorithm']=='KMeans+TF-IDF','实际算法不匹配')
    reqs=data(formal,'requirements','requirements.json');mappings=data(formal,'mapping','mappings.json')
    check(all(r['source_comment_ids'] and r['source_evidence_spans'] for r in reqs),'需求无评论证据')
    check(all(r['mapping_reason']['function_to_structure'] and r['mapping_reason']['requirement_to_function'] for r in mappings),'映射理由缺失')
    import re
    check(not re.search(r'主题\d+(优化功能|支撑结构)',str(reqs)+str(mappings)),'存在主题N模板')
    check(data(formal,'graph','graph.json')['used_graph_paths']==[],'未经人工审核被当作图谱')
    rec=data(formal,'generation','generation_records.json')
    check({g:sum(r['group']==g for r in rec) for g in ('A','B','C')}=={'A':5,'B':5,'C':5},'ABC数量错误')
    controls=[{k:r[k] for k in ('provider','model','parameters','task','output_format','image_count','retry_policy')} for r in rec]
    check(all(c==controls[0] for c in controls),'ABC控制变量不一致')
    check(all(r['mode']=='fake' and not r['is_real_ai'] for r in rec),'fake冒充真实AI')

    # Synthetic approval is a separate fixture run, never written into the formal experiment.
    fixture=root/'SIMULATED_FIXTURES';fixture.mkdir()
    reviewed=copy.deepcopy(mappings)
    for row in reviewed:row.update(review_status='approved',reviewer_id='SIM_REVIEWER01',reviewer_note='模拟审核fixture，仅用于测试链路，不是真实专家意见')
    review_path=write_json(fixture/'SIM_mapping_review.json',reviewed)
    sim_cfg=copy.deepcopy(cfg);sim_cfg['simulated']=True
    sim=run_experiment(sim_cfg,source,root/'simulated_reviewed',mapping_review=review_path)
    graph=data(sim,'graph','graph.json');paths=reconstruct(graph['nodes'],graph['edges'])
    check(bool(paths),'模拟审核图谱不能重建')
    sim_records=data(sim,'generation','generation_records.json')
    cs=[r for r in sim_records if r['group']=='C']
    check(all(r['used_graph_paths'] and json.loads(r['user_prompt'])['used_graph_paths']==r['used_graph_paths'] for r in cs),'图谱未进入真实Prompt')
    check(all(p['comment_id'] in r['used_comment_ids'] for r in cs for p in r['used_graph_paths']),'Prompt路径不能反查评论')
    reviews=[];changes=[];mapping=reviewed[0]
    for index,r in enumerate(cs):
        reviewer='SIM_R01';problem=f'模拟问题{index+1}：操作反馈需要调整'
        reviews.append(dict(reviewer_id=reviewer,background='SIM工业设计fixture',scheme_id=r['scheme_id'],evaluated_at='2026-09-06T00:00:00Z',strengths='模拟优点',issues=problem,suggestions='模拟建议：改善确认反馈',**{dim:2 for dim in DIMENSIONS}))
        payload=json.loads(r['user_prompt']);field='structure' if index==0 else 'controls'
        changes.append(dict(change_id=f'SIM_CH{index:02d}',v1_scheme_id=r['scheme_id'],v2_scheme_id='SIM_S'+uuid.uuid4().hex[:12].upper(),reviewer_id=reviewer,low_dimension='操作便利性',expert_issue=problem,requirement_id=mapping['requirement_id'],function_id=mapping['function_id'],structure_id=mapping['structure_id'],prompt_field=field,old_value=payload[field],new_value='模拟修改：放大确认组件并提供明确状态反馈',reason='模拟低分项设计推导，待真实二次评价'))
    rv=write_json(fixture/'SIM_V1_reviews.json',reviews);ch=write_json(fixture/'SIM_changes.json',changes)
    v2=run_experiment(sim_cfg,source,root/'simulated_v2',parent_run=sim,reviews=rv,changes=ch)
    second=[dict(row,scheme_id=change['v2_scheme_id'],**{dim:4 for dim in DIMENSIONS}) for row,change in zip(reviews,changes)]
    rv2=write_json(fixture/'SIM_V2_reviews.json',second)
    evaluated=run_experiment(sim_cfg,source,root/'simulated_second_evaluation',parent_run=v2,reviews=rv2)
    final_graph=data(evaluated,'graph','graph.json')
    check(final_graph==graph,'回评子运行未继承父审核图谱')
    stats=data(evaluated,'evaluation','v1_v2_comparison.json');chain=data(evaluated,'evaluation','v1_v2_chain.json')
    check(stats['n_independent_pairs']==5 and stats['dimensions']['操作便利性']['mean_difference']==2,'模拟配对统计不正确')
    check(not stats['can_claim_real_improvement'] and chain['status']=='simulated_loop_complete','模拟数据冒充真实改善')
    check(len(chain['changes'])==5,'修改链不完整')
    check(all(not r['independent_evaluation_completed'] for r in [data(formal,'report','completeness.json'),data(evaluated,'report','completeness.json')]),'伪造独立评价')
    for run in (formal,sim,evaluated):
        check(len(list(artifact(run,'evaluation','reviews.json').parent.joinpath('templates').glob('*.xlsx')))==6,'缺少人工模板')
    with zipfile.ZipFile(root/'blind_reviewer_package.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(artifact(sim,'generation','blind_schemes.json'),'blind_schemes.json')
        for name in ('abc_blind_review.xlsx','v1_v2_blind_review.xlsx'):z.write(artifact(sim,'evaluation',name),name)
    # Run both algorithms on the same input and configuration except algorithm.
    bert_cfg=copy.deepcopy(cfg);bert_cfg['topic']['algorithm']='bertopic'
    bert=run_experiment(bert_cfg,source,root/'bertopic');bm=verify_run(bert)
    bert_replica=run_experiment(bert_cfg,source,root/'bertopic_replica');brm=verify_run(bert_replica)
    for stage in compared:
        ah={Path(p).name:h for p,h in bm['stages'][stage]['outputs'].items() if p.endswith('.json')}
        bh={Path(p).name:h for p,h in brm['stages'][stage]['outputs'].items() if p.endswith('.json')}
        check(ah==bh,'BERTopic非AI结果不重复：'+stage)
    check(bm['actual_algorithm']=='BERTopic' and not bm['fallback_occurred'],'BERTopic错误命名或回退')
    bt=data(bert,'topics','topics.json');kt=data(formal,'topics','topics.json')
    from sklearn.metrics import adjusted_rand_score,normalized_mutual_info_score
    method_report={'input_sha256':a['input_sha256'],'same_input':bm['input_sha256']==a['input_sha256'],'kmeans_run':str(formal),'bertopic_run':str(bert),'kmeans_metrics':kt['metrics'],'bertopic_metrics':bt['metrics'],'adjusted_rand_index':float(adjusted_rand_score([r['topic_id'] for r in kt['assignments']],[r['topic_id'] for r in bt['assignments']])),'normalized_mutual_information':float(normalized_mutual_info_score([r['topic_id'] for r in kt['assignments']],[r['topic_id'] for r in bt['assignments']])),'interpretation':'描述性方法比较，无人工真值不宣称算法或设计优越'}
    write_json(root/'method_comparison.json',method_report)
    summary={'status':'passed','formal_run':str(formal.resolve()),'formal_manifest':str((formal/'run_manifest.json').resolve()),'replica_run':str(replica.resolve()),'bertopic_run':str(bert.resolve()),'simulated_reviewed_run':str(sim.resolve()),'simulated_v2_run':str(v2.resolve()),'simulated_second_evaluation_run':str(evaluated.resolve()),'counts':a['counts'],'deterministic_json_stages':compared,'abc_counts':{'A':5,'B':5,'C':5},'formal_approved_mappings':0,'simulated_approved_mappings':graph['approved_mapping_count'],'simulated_graph_paths':len(paths),'simulated_v1_v2_pairs':5,'real_expert_rows':0,'paid_api_calls':0,'static_quality_claims':False,'method_comparison':method_report,'manifest_hashes':{str(run.resolve()):sha256(run/'run_manifest.json') for run in (formal,replica,sim,v2,evaluated,bert)}}
    summary['bertopic_replica_run']=str(bert_replica.resolve())
    summary['bertopic_deterministic_json_stages']=compared
    summary['manifest_hashes'][str(bert_replica.resolve())]=sha256(bert_replica/'run_manifest.json')
    write_json(root/'acceptance.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('ACCEPTANCE_FILE='+str((root/'acceptance.json').resolve()))


if __name__=='__main__':main()
