from __future__ import annotations

import json
import re
from pathlib import Path

from experiment.pipeline.io import read_json


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower()=='.json':
        value=read_json(path)
        if isinstance(value,dict): value=value.get('rows')
        if not isinstance(value,list): raise ValueError('审核输入必须为行列表')
        return value
    import pandas as pd
    frame=pd.read_excel(path) if path.suffix.lower()=='.xlsx' else pd.read_csv(path,encoding='utf-8-sig')
    return frame.fillna('').to_dict('records')


def apply_reviews(candidates: list[dict], review_rows: list[dict], requirements: list[dict], *, simulated: bool=False) -> list[dict]:
    by_id={r['mapping_id']:dict(r) for r in candidates}; seen=set()
    reqs={r['requirement_id']:r for r in requirements}
    for source in review_rows:
        mid=source.get('mapping_id')
        if mid not in by_id or mid in seen: raise ValueError('审核存在未知或重复 mapping_id')
        seen.add(mid);original=by_id[mid]; row=dict(original)
        for key,value in source.items():
            if key in original and value not in ('',None):
                if isinstance(original[key],(dict,list)) and isinstance(value,str): value=json.loads(value)
                row[key]=value
        decision=source.get('review_decision','')
        if decision:
            if decision not in ('agree','modify','reject'):raise ValueError('review_decision必须为agree/modify/reject')
            expected={'agree':'approved','modify':'pending_review','reject':'rejected'}[decision]
            if source.get('review_status') not in ('',None,'pending_review',expected):raise ValueError('审核操作与状态冲突')
            row['review_status']=expected
            if not row.get('reviewed_at') or not row.get('knowledge_source'):raise ValueError('审核操作必须填写reviewed_at与knowledge_source')
            from datetime import datetime
            try:datetime.fromisoformat(str(row['reviewed_at']).replace('Z','+00:00'))
            except ValueError:raise ValueError('reviewed_at必须为ISO 8601时间') from None
        # Evidence and identity are immutable; a new relationship requires a new candidate/version.
        for key in ('requirement_id','source_comment_ids','evidence_spans','function_id','structure_id'):
            if row[key]!=original[key]: raise ValueError('审核不得更换映射身份或原始证据')
        if row['review_status'] not in ('pending_review','approved','rejected'): raise ValueError('非法审核状态')
        if row['review_status']=='approved':
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]+',str(row['reviewer_id'])) or not row['reviewer_note'].strip():
                raise ValueError('通过审核必须填写匿名 reviewer_id 和审核意见')
            if row['reviewer_id'].upper().startswith(('SIM','FAKE','DEMO')) and not simulated:
                raise ValueError('模拟审核不得进入正式实验')
            reasons=row['mapping_reason']
            if not isinstance(reasons,dict) or not all(str(reasons.get(k,'')).strip() for k in ('requirement_to_function','function_to_structure')):
                raise ValueError('必须分别填写两条关系的映射理由')
            for key in ('requirement_name','function_name','structure_name'):
                if not isinstance(row[key],str) or not row[key].strip() or re.search(r'主题\d+|待人工',row[key]): raise ValueError('审核关系缺少实际语义')
            if row['requirement_id'] not in reqs: raise ValueError('审核需求不存在')
            row['mapping_version']='rfs-reviewed-v2';row['simulated']=simulated
        by_id[mid]=row
    return list(by_id.values())


def build_graph(mappings: list[dict], comments: list[dict], *, simulated=False) -> dict:
    comments_by_id={r['comment_id']:r for r in comments}; nodes={};edges=[];paths=[]
    for row in mappings:
        if row['review_status']!='approved':continue
        if not row.get('reviewer_id') or not row.get('reviewer_note') or not row.get('source_comment_ids'):
            raise ValueError('已审核图谱关系缺少审核者、意见或评论证据')
        if not isinstance(row.get('mapping_reason'),dict) or not all(row['mapping_reason'].get(k) for k in ('requirement_to_function','function_to_structure')):
            raise ValueError('已审核图谱缺少关系理由')
        if row.get('simulated') and not simulated: raise ValueError('模拟关系禁止进入正式图谱')
        for key,kind,label_key in [('requirement_id','Requirement','requirement_name'),('function_id','Function','function_name'),('structure_id','Structure','structure_name')]:
            nodes[row[key]]=dict(id=row[key],type=kind,label=row[label_key])
        for cid in row['source_comment_ids']:
            if cid not in comments_by_id: raise ValueError('图谱评论证据不存在')
            if not any(s.get('comment_id')==cid and s.get('text') in comments_by_id[cid]['cleaned_comment'] for s in row['evidence_spans']):raise ValueError('图谱证据片段与评论不一致')
            nodes[cid]=dict(id=cid,type='Comment',label=comments_by_id[cid]['cleaned_comment'])
            edges.append(dict(source=cid,target=row['requirement_id'],type='SUPPORTS',mapping_id=row['mapping_id'],reason='评论语境经审核支持用户目标'))
            paths.append(dict(path_id=f'{row["mapping_id"]}_{cid}',comment_id=cid,comment_evidence=comments_by_id[cid]['cleaned_comment'],requirement_id=row['requirement_id'],requirement_name=row['requirement_name'],function_id=row['function_id'],function_name=row['function_name'],structure_id=row['structure_id'],structure_name=row['structure_name'],mapping_id=row['mapping_id'],mapping_reason=row['mapping_reason'],reviewer_id=row['reviewer_id'],simulated=simulated))
        edges.extend([dict(source=row['requirement_id'],target=row['function_id'],type='REALIZED_BY',mapping_id=row['mapping_id'],reason=row['mapping_reason']['requirement_to_function']),dict(source=row['function_id'],target=row['structure_id'],type='CARRIED_BY',mapping_id=row['mapping_id'],reason=row['mapping_reason']['function_to_structure'])])
    return dict(nodes=sorted(nodes.values(),key=lambda r:r['id']),edges=edges,used_graph_paths=paths,approved_mapping_count=sum(r['review_status']=='approved' for r in mappings),evidence_status=('模拟审核图谱证据' if simulated else '已审核图谱证据') if paths else '无正式图谱证据',simulated=simulated)


def reconstruct(nodes: list[dict],edges: list[dict]) -> list[list[str]]:
    by_id={r['id']:r for r in nodes};adj={}
    allowed={('Comment','SUPPORTS','Requirement'),('Requirement','REALIZED_BY','Function'),('Function','CARRIED_BY','Structure')}
    for edge in edges:
        if edge['source'] not in by_id or edge['target'] not in by_id: raise ValueError('图谱边引用不存在的节点')
        if (by_id[edge['source']]['type'],edge['type'],by_id[edge['target']]['type']) not in allowed: raise ValueError('图谱边类型无效')
        adj.setdefault(edge['source'],[]).append(edge['target'])
    return [[c,r,f,s] for c in by_id if by_id[c]['type']=='Comment' for r in adj.get(c,[]) for f in adj.get(r,[]) for s in adj.get(f,[])]
