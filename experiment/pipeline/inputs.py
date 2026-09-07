"""Evidence-factor transparency. Group keys stay in private experiment materials."""
import json
import re
from experiment.pipeline.io import digest, write_json
from experiment.pipeline.generation import SYSTEM_PROMPT


def export_inputs(directory, inputs, config):
    directory.mkdir(parents=True, exist_ok=True)
    rows=[]
    fields=sorted(set().union(*(p.keys() for p in inputs.values())))
    for group,payload in inputs.items():
        user=json.dumps(payload,ensure_ascii=False,sort_keys=True)
        write_json(directory/(group+'.json'),dict(system_prompt=SYSTEM_PROMPT,user_prompt=user,
            parameters=config['generation']['parameters'],model=config['generation']['model'],
            input_characters=len(SYSTEM_PROMPT)+len(user),input_utf8_bytes=len((SYSTEM_PROMPT+user).encode()),
            token_count='unknown_until_provider_response',payload_sha256=digest(payload)))
    for field in fields:
        values={g:p[field] for g,p in inputs.items()}
        rows.append(dict(field=field,equal_across_groups=len({digest(v) for v in values.values()})==1,
                         factor='审核映射路径' if field=='used_graph_paths' else ('评论证据' if field in ('requirements','comments','comment_specific_constraints') else '共同控制变量'),
                         groups={g:dict(sha256=digest(v),characters=len(json.dumps(v,ensure_ascii=False))) for g,v in values.items()}))
    write_json(directory/'input_difference_table.json',rows)
    lines=['# A/B/C 输入差异表','', 'A：基础任务与通用约束；B：A＋需求与代表评论；C：B＋审核路径。',
           '评论特定约束字段当前为空，不自动推断或混入通用约束。B/C仅检验加入审核路径的作用，不能证明图谱优于表格。',
           '输入信息量与长度有意不同，输出token预算一致；真实用量以服务端响应为准。','', '| 字段 | 三组相同 | 实验因素 |','|---|---|---|']
    lines += [f'| {r["field"]} | {r["equal_across_groups"]} | {r["factor"]} |' for r in rows]
    (directory/'input_difference_table.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def blindness_audit(blind):
    findings=[]
    for row in blind:
        if set(row)!={'scheme_id','content'}:
            findings.append(dict(scheme_id=row.get('scheme_id'),reason='unexpected_fields'))
        if re.search(r'(?i)(?:\bgroup\s*[ABC]\b|[ABC]\s*组|实验组\s*[:：]|\bV[12]\b)',row.get('content','')):
            findings.append(dict(scheme_id=row.get('scheme_id'),reason='possible_explicit_group_or_version_leak'))
    return dict(status='needs_manual_review' if findings else 'no_explicit_group_labels_detected',findings=findings,
        note='仅检查显式标签；方案内容可能透露输入丰富度，仍需真实人员盲法核查。不提供私有输入/组别表给评委。')
