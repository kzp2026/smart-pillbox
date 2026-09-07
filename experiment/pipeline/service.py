from __future__ import annotations

import copy
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime,timezone
from pathlib import Path

from experiment import METHOD_VERSION
from experiment.pipeline.io import digest,inside,read_json,sha256,table,write_json

ROOT=Path(__file__).resolve().parents[1]
STAGES=('clean','topics','requirements','mapping','graph','generation','evaluation','report')


def now(): return datetime.now(timezone.utc).isoformat()


def source_hashes():
    paths=[p for p in ROOT.rglob('*.py') if not any(x in p.parts for x in ('runs','verification','__pycache__'))]
    paths += list(ROOT.glob('requirements*.txt')) + [ROOT/'config.example.json']
    paths += list((ROOT/'models').glob('*.json')) if (ROOT/'models').exists() else []
    paths += list((ROOT/'schemas').glob('*.json'))
    result={str(p.relative_to(ROOT)).replace('\\','/'):sha256(p) for p in sorted(paths)}
    # Strict research generation reuses this V2 provider; include its exact source too.
    for relative in ('../v2/__init__.py','../v2/providers/__init__.py','../v2/providers/text.py'):
        result[relative]=sha256(ROOT/relative)
    return result


def validate_config(config: dict) -> dict:
    cfg=copy.deepcopy(config)
    example=read_json(ROOT/'config.example.json')
    def check(value,expected):
        if expected is not None and not isinstance(expected,dict):
            allowed=(int,float) if type(expected) is float else (type(expected),)
            if type(value) not in allowed:raise ValueError('配置字段类型不符合固定规范')
        if expected is None and value is not None:raise ValueError('当前方法版本不支持此默认空值参数变更')
        if isinstance(value,dict):
            for key,child in value.items():
                if re.search(r'api.?key|password|secret|credential|database.?url|access.?token',key,re.I):raise ValueError('配置不得包含 Secrets')
                if not isinstance(expected,dict) or key not in expected:raise ValueError('配置存在未知字段：'+key)
                if key=='industrial_constraints':
                    if not isinstance(child,dict) or any(not isinstance(v,str) for v in child.values()):raise ValueError('工业设计约束必须为文本字段')
                    for k in child:
                        if re.search(r'key|secret|password|token',k,re.I):raise ValueError('约束不得包含 Secrets')
                else:check(child,expected[key])
            if isinstance(expected,dict) and set(value)!=set(expected):raise ValueError('配置缺少必填字段')
    check(cfg,example)
    if cfg['method_version']!=METHOD_VERSION:raise ValueError('方法版本不匹配')
    if type(cfg['seed']) is not int or not 0<=cfg['seed']<=2**32-1:raise ValueError('随机种子无效')
    if cfg['topic']['algorithm'] not in ('kmeans_tfidf','bertopic'):raise ValueError('必须明确选择实际主题算法')
    if type(cfg['topic']['n_topics']) is not int or not 1<=cfg['topic']['n_topics']<=30:raise ValueError('主题数必须在1–30')
    weights=cfg['importance']
    if any(type(v) not in (int,float) or not 0<=v<=1 for v in weights.values()) or abs(sum(weights.values())-1)>1e-8:raise ValueError('重要度权重必须归一化且和为1')
    g=cfg['generation']
    if g['mode'] not in ('test','research','transport_test'):raise ValueError('必须明确研究或测试模式')
    if g['mode']=='test' and (g['provider']!='fake' or g['model']!='fake-design-v1'):raise ValueError('fake测试模式仅允许固定fake模型')
    if g['mode']!='test' and (g['provider']!='deepseek' or not g['model'].strip()):raise ValueError('真实接口必须显式指定deepseek及准确模型名')
    if g['mode']=='research' and cfg['simulated']:raise ValueError('正式研究禁止模拟数据审核')
    if g['mode']=='transport_test' and not cfg['simulated']:raise ValueError('mock真实接口仅可用于明确模拟运行')
    if not g['groups'] or len(set(g['groups']))!=len(g['groups']) or any(group not in ('A','B','C') for group in g['groups']):raise ValueError('实验组必须为不重复的A/B/C子集')
    if type(g['repetitions']) is not int or not 1<=g['repetitions']<=100:raise ValueError('每组生成次数必须在1–100')
    if g['image_count']!=0:raise ValueError('fake 验收图片数量必须为0；不伪造真实图片生成')
    if not 0<=g['retry_policy']['max_retries']<=3:raise ValueError('重试次数必须在0–3')
    if type(cfg['simulated']) is not bool:raise ValueError('simulated 必须是布尔值')
    if cfg['topic']['embedding']['device']!='cpu':raise ValueError('此方法版本锁定CPU以保证可复现')
    if cfg['cleaning']['min_length']<1:raise ValueError('评论最小长度必须为正数')
    if not 0<=g['parameters']['temperature']<=2 or g['parameters']['max_tokens']<1:raise ValueError('生成参数不合法')
    if not cfg['product_name'].strip():raise ValueError('产品名不能为空')
    return cfg


def read_manifest(run: Path) -> dict: return read_json(Path(run)/'run_manifest.json')


def artifact(run: Path, stage: str, filename: str) -> Path:
    manifest=read_manifest(run);state=manifest['stages'].get(stage,{})
    if state.get('status')!='completed':raise ValueError('上游阶段未成功完成：'+stage)
    matches=[p for p in state['outputs'] if Path(p).name==filename]
    if len(matches)!=1:raise ValueError('本次阶段产物缺失或不唯一：'+filename)
    path=inside(run,matches[0])
    if sha256(path)!=state['outputs'][matches[0]]:raise ValueError('上游文件哈希不一致：'+filename)
    return path


def verify_run(run: Path) -> dict:
    manifest=read_manifest(run)
    from experiment.pipeline.schemas import validate
    validate('manifest',manifest)
    if digest(read_json(run/'config.json'))!=manifest['config_sha256']:raise ValueError('配置哈希不一致')
    for p,h in manifest['input_files'].items():
        if sha256(inside(run,p))!=h:raise ValueError('输入哈希不一致')
    for stage in manifest['stages'].values():
        for p,h in {**stage['inputs'],**stage['outputs']}.items():
            if sha256(inside(run,p))!=h:raise ValueError('阶段文件哈希不一致：'+p)
    for p,h in manifest.get('supplemental_artifacts',{}).items():
        if sha256(inside(run,p))!=h:raise ValueError('补充审核材料哈希不一致：'+p)
    return manifest


def run_experiment(config: dict,input_path: Path,runs_root: Path | None=None,*,mapping_review: Path | None=None,reviews: Path | None=None,changes: Path | None=None,annotations: Path | None=None,parent_run: Path | None=None,stop_after: str | None=None,provider=None) -> Path:
    cfg=validate_config(config);input_path=Path(input_path).resolve()
    if not input_path.is_file():raise ValueError('原始评论输入不存在')
    if input_path.suffix.lower() not in ('.csv','.xlsx'):raise ValueError('仅支持 CSV/XLSX 评论输入')
    rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12]
    run=((Path(runs_root) if runs_root else ROOT/'runs'/cfg['generation']['mode'])/rid).resolve()
    run.mkdir(parents=True,exist_ok=False);(run/'private').mkdir()
    shutil.copyfile(input_path,run/'private'/('input'+input_path.suffix.lower()))
    write_json(run/'config.json',cfg)
    inputs={str(p.relative_to(run)).replace('\\','/'):sha256(p) for p in (run/'private').iterdir()}
    optional={}
    for name,path in dict(mapping_review=mapping_review,reviews=reviews,changes=changes,annotations=annotations).items():
        if path:
            path=Path(path);dest=run/'private'/(name+path.suffix.lower());shutil.copyfile(path,dest)
            relative=str(dest.relative_to(run)).replace('\\','/');optional[name]=relative;inputs[relative]=sha256(dest)
    if parent_run:
        parent_run=Path(parent_run);pm=verify_run(parent_run)
        if pm['input_sha256']!=sha256(input_path) or pm['config_sha256']!=digest(cfg):raise ValueError('父运行输入或配置不一致，请使用相同数据和配置')
        optional['parent_run_id']=pm['run_id']
        for stage,filename in [('generation','generation_records.json'),('mapping','mappings.json'),('requirements','requirements.json'),('evaluation','reviews.json'),('evaluation','v1_v2_chain.json')]:
            dest=run/'private'/('parent_'+filename);shutil.copyfile(artifact(parent_run,stage,filename),dest)
            relative=str(dest.relative_to(run)).replace('\\','/');optional['parent_'+filename]=relative;inputs[relative]=sha256(dest)
    def git(*args):
        try:return subprocess.check_output(['git',*args],cwd=ROOT.parent,text=True,encoding='utf-8',stderr=subprocess.DEVNULL).strip()
        except (subprocess.CalledProcessError,FileNotFoundError):return 'unavailable_source_archive'
    sources=source_hashes()
    for relative,h in sources.items():
        dest=(run/'source'/'experiment'/relative).resolve();dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,dest)
        inputs[dest.relative_to(run).as_posix()]=h
    deps={d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name']}
    manifest=dict(run_id=rid,method_version=METHOD_VERSION,started_at=now(),finished_at=None,status='running',git_commit=git('rev-parse','HEAD'),workspace_dirty=bool(git('status','--porcelain')),python=sys.version,operating_system=platform.platform(),dependencies=dict(sorted(deps.items())),input_path=str(input_path),input_sha256=sha256(input_path),input_files=inputs,optional_inputs=optional,counts={},requested_algorithm=cfg['topic']['algorithm'],actual_algorithm=None,algorithm_parameters=cfg['topic'],random_seed=cfg['seed'],stages={},provider=cfg['generation']['provider'],model=cfg['generation']['model'],generation_parameters=cfg['generation'],prompts=[],retry_occurred=False,fallback_occurred=False,error_summary='',artifacts=[],config_sha256=digest(cfg),source_files=source_hashes(),importance_formula={'formula':'0–1 normalized frequency * w_f + negative_ratio * w_n + specificity * w_s','normalization':{'frequency':'matched comment count / valid comment count','negative_ratio':'negative lexicon matches / requirement evidence count','specificity':'evidence text length >=15 / requirement evidence count'},'weights':cfg['importance']},simulated=cfg['simulated'],external_api_calls=0,data_status=cfg['data_status'])
    manifest['source_files']=sources
    manifest['experiment_mode']=cfg['generation']['mode']
    manifest['inference_design']=cfg['inference_design']
    manifest['inference_design_sha256']=digest(cfg['inference_design'])
    write_json(run/'run_manifest.json',manifest)
    try:
        _execute(run,cfg,0,stop_after,provider=provider)
    except Exception as exc:
        exc.run_path = run
        raise
    return run


def resume_experiment(run: Path,config: dict,from_stage: str,*,stop_after=None,provider=None) -> Path:
    run=Path(run);cfg=validate_config(config);m=read_manifest(run)
    if digest(cfg)!=m['config_sha256']:raise ValueError('续跑配置与原运行不一致')
    verify_run(run)
    if source_hashes()!=m['source_files']:raise ValueError('源码版本变化，请创建新运行，不可续跑')
    if m.get('embedding_file_hashes'):
        from experiment.pipeline.topics import verify_embedding
        if verify_embedding(cfg['topic']['embedding'])!=m['embedding_file_hashes']:raise ValueError('嵌入模型哈希已变化，请创建新运行')
    if from_stage not in STAGES:raise ValueError('未知续跑阶段')
    index=STAGES.index(from_stage)
    if index<=STAGES.index('generation') and any(r.get('request_sent') for r in m.get('generation_calls',{}).values()):
        raise ValueError('本运行已有真实请求，禁止自动重发收费批次；保留原记录并显式创建新实验，或仅续跑evaluation/report')
    if any(m['stages'].get(s,{}).get('status')!='completed' for s in STAGES[:index]):raise ValueError('续跑上游未完成')
    _execute(run,cfg,index,stop_after,provider=provider);return run


def _execute(run: Path,cfg: dict,start: int,stop_after=None,*,provider=None):
    m=read_manifest(run);m.update(status='running',error_summary='',finished_at=None)
    if m.get('supplemental_artifacts'):
        m['artifacts']=[p for p in m['artifacts'] if p not in m['supplemental_artifacts']]
        m.setdefault('previous_supplemental_artifacts',[]).append(m.pop('supplemental_artifacts'))
    for downstream in STAGES[start:]:
        if downstream in m['stages']:
            m.setdefault('previous_attempts',[]).append(dict(stage=downstream,**m['stages'][downstream]))
            m['stages'][downstream]={**m['stages'][downstream],'status':'invalidated_by_resume'}
    write_json(run/'run_manifest.json',m)
    # Attempts are append-only; preserve all prior artifacts while advancing current stage pointers.
    for stage in STAGES[start:]:
        directory=run/'stages'/stage/uuid.uuid4().hex[:12];directory.mkdir(parents=True)
        deps={p:h for p,h in m['input_files'].items()}
        deps['config.json']=sha256(run/'config.json')
        for upstream in STAGES[:STAGES.index(stage)]:deps.update(m['stages'][upstream]['outputs'])
        state=dict(started_at=now(),finished_at=None,status='running',inputs=deps,outputs={},error_summary='')
        previous=m['stages'].get(stage)
        if previous:m.setdefault('previous_attempts',[]).append(dict(stage=stage,**previous))
        m['stages'][stage]=state;write_json(run/'run_manifest.json',m)
        try:
            for p,h in deps.items():
                if sha256(inside(run,p))!=h:raise ValueError('阶段输入哈希不一致')
            _stage(stage,run,directory,cfg,m,provider=provider)
            from experiment.pipeline.schemas import validate
            checks={'requirements.json':'requirement','approved_requirements.json':'requirement','mappings.json':'mapping','generation_records.json':'generation'}
            for p in directory.rglob('*.json'):
                if p.name in checks:
                    for row in read_json(p):validate(checks[p.name],row)
            state.update(status='completed',finished_at=now(),outputs={str(p.relative_to(run)).replace('\\','/'):sha256(p) for p in sorted(directory.rglob('*')) if p.is_file()})
            m['artifacts']=sorted(set(m['artifacts'])|set(state['outputs']))
            write_json(run/'run_manifest.json',m)
            if stage==stop_after:
                m.update(status='paused',finished_at=now());write_json(run/'run_manifest.json',m);return
        except Exception as exc:
            summary=str(exc) if isinstance(exc,(ValueError,ImportError,RuntimeError)) else type(exc).__name__+'：阶段失败，请检查本地依赖与输入格式'
            state.update(status='failed',finished_at=now(),error_summary=summary,outputs={str(p.relative_to(run)).replace('\\','/'):sha256(p) for p in directory.rglob('*') if p.is_file()})
            m.update(status='failed',finished_at=now(),error_summary=summary)
            write_json(run/'run_manifest.json',m)
            raise
    m.update(status='completed',finished_at=now());write_json(run/'run_manifest.json',m)


def _stage(stage,run,out,cfg,m,*,provider=None):
    def get(s,name):return read_json(artifact(run,s,name))
    def optional(name):
        from experiment.pipeline.graph import read_rows
        p=m['optional_inputs'].get(name)
        if p and name=='reviews' and p.endswith('.xlsx'):
            from experiment.evaluation.templates import read_review_file
            return read_review_file(inside(run,p))
        if p and name=='mapping_review' and p.endswith('.xlsx'):
            from experiment.evaluation.templates import import_mapping_reviews
            return import_mapping_reviews(inside(run,p))
        return read_rows(inside(run,p)) if p else []
    def parent_file(name,default):
        p=m['optional_inputs'].get('parent_'+name);return read_json(inside(run,p)) if p else default
    if stage=='clean':
        from experiment.pipeline.cleaning import clean_input
        source=next(p for p in m['input_files'] if Path(p).stem=='input')
        rows,audit,counts=clean_input(inside(run,source),cfg['cleaning']);m['counts']=counts
        write_json(out/'comments.json',rows);write_json(out/'cleaning_audit.json',audit);write_json(out/'counts.json',counts)
        table(out/'cleaning_audit.xlsx',{'清洗审计':audit,'保留评论':rows})
    elif stage=='topics':
        from experiment.pipeline.topics import cluster
        result=cluster(get('clean','comments.json'),cfg['topic'],cfg['seed']);m['actual_algorithm']=result['actual_algorithm']
        name='BERTopic' if result['actual_algorithm']=='BERTopic' else 'KMeans_TFIDF'
        write_json(out/'topics.json',result);table(out/(name+'_主题聚类结果.xlsx'),{name+'_评论聚类':result['assignments'],name+'_主题汇总':result['topic_summary']})
        m['embedding_file_hashes']=result['embedding_file_hashes']
    elif stage=='requirements':
        from experiment.pipeline.semantics import derive_requirements
        rows=parent_file('requirements.json',None)
        if rows is None:rows=derive_requirements(get('clean','comments.json'),get('topics','topics.json'),cfg['importance'])
        write_json(out/'requirements.json',rows);table(out/'需求证据候选.xlsx',{'需求候选':rows})
        annotations=[]
        if m['optional_inputs'].get('annotations'):
            from experiment.evaluation.templates import import_annotations
            comments=get('clean','comments.json');by_id={r['comment_id']:r for r in comments}
            annotations=import_annotations(inside(run,m['optional_inputs']['annotations']),by_id,{r['requirement_id'] for r in rows})
            for annotation in annotations:
                if cfg['generation']['mode']=='research' and annotation['annotator_id'].upper().startswith(('SIM','FAKE','DEMO')):raise ValueError('模拟标注不得进入正式研究')
                key='original_comment' if 'original_comment' in annotation else 'cleaned_comment'
                if annotation[key]!=by_id[annotation['comment_id']][key]:raise ValueError('标注表原始证据被改写，请恢复本run评论文本')
        write_json(out/'human_annotations.json',annotations)
    elif stage=='mapping':
        from experiment.pipeline.semantics import candidate_mappings
        from experiment.pipeline.graph import apply_reviews
        reqs=get('requirements','requirements.json');candidates=candidate_mappings(reqs)
        if m['optional_inputs'].get('parent_run_id') and m['optional_inputs'].get('mapping_review'):
            raise ValueError('评价或修改子运行不可替换父审核关系；请创建独立新实验')
        rows=parent_file('mappings.json',None)
        if rows is None:rows=apply_reviews(candidates,optional('mapping_review'),reqs,simulated=cfg['simulated'])
        write_json(out/'mappings.json',rows);table(out/'需求功能结构映射.xlsx',{'候选及审核关系':rows})
        formal=[]
        for row in rows:
            if row['review_status']=='approved':
                req=next(r for r in reqs if r['requirement_id']==row['requirement_id'])
                formal.append(dict(req,requirement_name=row['requirement_name'],review_status='approved',reviewer_id=row['reviewer_id'],reviewer_note=row['reviewer_note'],semantic_naming_method='human_review_of_rule_candidate',simulated=cfg['simulated']))
        write_json(out/'approved_requirements.json',formal)
    elif stage=='graph':
        from experiment.pipeline.graph import build_graph,reconstruct
        graph=build_graph(get('mapping','mappings.json'),get('clean','comments.json'),simulated=cfg['simulated'])
        write_json(out/'graph.json',graph);write_json(out/'nodes.json',graph['nodes']);write_json(out/'edges.json',graph['edges']);write_json(out/'reconstructed_paths.json',reconstruct(graph['nodes'],graph['edges']))
    elif stage=='generation':
        from experiment.pipeline.generation import generate_groups,revise_records,build_inputs,validate_generation_gate
        from experiment.pipeline.inputs import export_inputs
        if cfg['generation']['mode']=='research':
            for row in optional('reviews')+optional('changes')+parent_file('reviews.json',[]):
                if str(row.get('reviewer_id','')).upper().startswith(('SIM','FAKE','DEMO')):raise ValueError('模拟评价或修改不得进入正式研究')
        export_inputs(out/'private'/'inputs',build_inputs(cfg,get('requirements','requirements.json'),get('clean','comments.json'),get('graph','graph.json')),cfg)
        validate_generation_gate(cfg,get('graph','graph.json'),provider)
        if cfg['generation']['provider']!='fake' and provider is None:
            from experiment.pipeline.providers import configured_provider
            provider=configured_provider(cfg['generation'])
        if cfg['generation']['mode']=='transport_test' and not getattr(provider,'transport_is_mock',False):
            raise ValueError('transport_test只能使用显式mock传输，禁止网络调用')
        def journal(record):
            write_json(out/'private'/'attempts'/(record['generation_id']+'.json'),record)
            prompt=write_json(out/'private'/'prompts'/(record['generation_id']+'.json'),{'system_prompt':record['system_prompt'],'user_prompt':record['user_prompt'],'parameters':record['parameters']})
            item=dict(path=prompt.relative_to(run).as_posix(),sha256=sha256(prompt))
            m['prompts']=[p for p in m['prompts'] if p['path']!=item['path']]+[item]
            m['retry_occurred']=m['retry_occurred'] or bool(record['retry_count'])
            m.setdefault('generation_calls',{})[record['generation_id']]=dict(status=record['status'],mode=record['mode'],request_sent=record.get('request_sent',False),attempt_count=record['retry_count']+1,transport_is_mock=record.get('transport_is_mock',cfg['generation']['mode']=='transport_test'))
            m['external_api_calls']=sum(r['attempt_count'] for r in m['generation_calls'].values() if r['request_sent'])
            m['external_api_attempts']=m['external_api_calls']
            m['external_api_completed']=sum(r['request_sent'] and r['status']=='completed' for r in m['generation_calls'].values())
            m['external_api_unknown_outcome_attempts']=m['external_api_attempts']-m['external_api_completed']
            write_json(run/'run_manifest.json',m)
        parents=parent_file('generation_records.json',[]);changes=optional('changes')
        chain=parent_file('v1_v2_chain.json',{'changes':[],'pairs':[]})
        if parents:
            if changes:
                prior_reviews=parent_file('reviews.json',[])+optional('reviews')
                records,checked,pairs=revise_records(m['run_id'],cfg,parents,changes,prior_reviews,get('requirements','requirements.json'),get('mapping','mappings.json'),on_record=journal,provider=provider)
                chain={'changes':checked,'pairs':pairs}
            else:records=parents
            blind=[dict(scheme_id=r['scheme_id'],content=r['raw_response']) for r in records]
            import random
            random.SystemRandom().shuffle(blind)
            assignments=[dict(scheme_id=r['scheme_id'],generation_id=r['generation_id'],group=r['group'],version=r['result_version']) for r in records]
            m['generation_reuses_parent']=not bool(changes)
        else:
            if changes:raise ValueError('V1—V2修改必须指定父运行')
            records,blind,assignments=generate_groups(m['run_id'],cfg,get('requirements','requirements.json'),get('clean','comments.json'),get('graph','graph.json'),on_record=journal,provider=provider)
        write_json(out/'private'/'revision_chain.json',chain)
        write_json(out/'private'/'generation_records.json',records);write_json(out/'private'/'scheme_group_mapping.json',assignments)
        write_json(out/'blind'/'blind_schemes.json',blind)
        from experiment.pipeline.inputs import blindness_audit
        write_json(out/'private'/'blindness_audit.json',blindness_audit(blind))
        for r in records:
            journal(r)
        m['retry_occurred']=any(r['retry_count'] for r in records)
    elif stage=='evaluation':
        from experiment.evaluation.templates import create_templates
        from experiment.evaluation.statistics import validate_reviews,summarize_reviews,compare_versions
        records=get('generation','generation_records.json');blind=get('generation','blind_schemes.json')
        reviews=validate_reviews(parent_file('reviews.json',[])+optional('reviews'),{r['scheme_id'] for r in records})
        summary=summarize_reviews(reviews,simulated=cfg['simulated'] or any(r['mode']=='fake' for r in records))
        write_json(out/'reviews.json',reviews);write_json(out/'evaluation_statistics.json',summary)
        chain=get('generation','revision_chain.json');pairs=chain.get('pairs',[])
        comparison=compare_versions(reviews,pairs,simulated=cfg['simulated'] or any(r.get('simulated',r['mode']=='fake') for r in records),design=cfg['inference_design'])
        write_json(out/'v1_v2_comparison.json',comparison)
        complete=bool(pairs) and comparison['n_independent_pairs']==len(pairs)
        chain['status']=('simulated_loop_complete' if cfg['simulated'] or any(r['mode']=='fake' for r in records) else 'independent_loop_complete') if complete else 'awaiting_real_expert_evaluation'
        write_json(out/'v1_v2_chain.json',chain)
        annotations=[]
        if m['optional_inputs'].get('annotations'):
            from experiment.evaluation.templates import import_annotations
            annotations=import_annotations(inside(run,m['optional_inputs']['annotations']),{r['comment_id'] for r in get('clean','comments.json')},{r['requirement_id'] for r in get('requirements','requirements.json')})
        write_json(out/'human_annotations.json',annotations)
        create_templates(out/'templates',get('clean','comments.json'),get('requirements','requirements.json'),get('mapping','mappings.json'),blind)
        from experiment.evaluation.materials import prepare_review_materials
        prepare_review_materials(run,out/'human_materials')
    elif stage=='report':
        graph=get('graph','graph.json');records=get('generation','generation_records.json');reviews=get('evaluation','reviews.json')
        check=dict(kind='流程完整度检查',comment_evidence_present=bool(get('clean','comments.json')),approved_mapping_count=graph['approved_mapping_count'],graph_evidence_status=graph['evidence_status'],prompt_saved=all(r['system_prompt'] and r['user_prompt'] for r in records),model_parameters_saved=all(r['parameters'] for r in records),required_stages_present=all(s in m['stages'] for s in STAGES),independent_evaluation_completed=bool(reviews) and cfg['generation']['mode']=='research' and {r['scheme_id'] for r in records}=={r['scheme_id'] for r in reviews} and all(r.get('is_real_ai') for r in records),v1_v2_loop_completed=get('evaluation','v1_v2_chain.json')['status']=='independent_loop_complete',simulated_loop_completed=get('evaluation','v1_v2_chain.json')['status']=='simulated_loop_complete',generation_mode=cfg['generation']['mode'],method_version=METHOD_VERSION,actual_algorithm=m['actual_algorithm'],evidence_count=m['counts']['valid'])
        write_json(out/'completeness.json',check)
        text=f'# 论文实验运行 {m["run_id"]}\n\n方法版本：{METHOD_VERSION}；实际算法：{m["actual_algorithm"]}；未发生算法回退。\n\n原始 {m["counts"]["raw"]} 条，有效 {m["counts"]["valid"]} 条，重复合并 {m["counts"]["duplicate"]} 条，删除 {m["counts"]["removed"]} 条。\n\n{graph["evidence_status"]}，审核映射 {graph["approved_mapping_count"]} 条。自动语义命名和映射均为设计推导候选，需人工复核。\n\nA/B/C 每组 {cfg["generation"]["repetitions"]} 次，生成模式 {cfg['generation']['mode']}，provider {cfg['generation']['provider']}，图片数 0；是否构成真实对照数据须核实审核、调用与评价记录。\n\n旧自动分数不是方案质量评价。本次仅检查证据、映射、Prompt、参数和文件完整度，无独立专家数据不产生显著性结论。\n\n正式输出只包含匿名评论 ID；原始输入位于 private，禁止作为公开盲评包发布。\n'
        (out/'report.md').write_text(text,encoding='utf-8')
