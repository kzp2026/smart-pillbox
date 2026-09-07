"""One versioned design coding vocabulary, shared by CLI and V2. Rules are hypotheses, not human evidence."""
from __future__ import annotations

import re
from collections import Counter

from experiment.pipeline.io import digest

# key, user goal, trigger terms, product behavior, physical/interaction carrier
CATALOG = (
 ('reminder','清晰感知并确认服药提醒',('提醒','提示','声音','灯光','通知','忘记','按时','闹钟','定时','语音'),'按计划发出多模态提醒并记录服药确认','扬声器、LED指示灯、时钟模块与确认按键'),
 ('operation','低负担完成设置和取药操作',('方便','简单','容易','操作','老人','父母','清楚','按键','设置'),'简化设置步骤并提供清晰的状态引导','大尺寸实体按键、高对比显示屏与图文标签'),
 ('storage','按时段清晰分类和取用药品',('容量','收纳','分格','分类','空间','够用','药仓','几格','四格','4格','七天'),'按服药时段分格存储并引导取用','可拆卸分格药仓、透明翻盖与时段标识'),
 ('moisture','保持药品干燥并避免污染',('防潮','密封','受潮','干燥','防水','卫生'),'隔离湿气并支持清洁维护','硅胶密封圈、密闭盖与可拆卸内胆'),
 ('portable','轻便携带日常所需药品',('便携','携带','小巧','体积','轻便','旅行'),'减小携带体积并固定药仓','紧凑壳体、锁扣与圆角握持边缘'),
 ('remote','远程了解服药状态和异常',('远程','微信','蓝牙','手机','联网','app','监护','连接'),'同步服药记录并发送异常通知','无线通信模块、配网按键与监护端界面'),
 ('safety','避免误操作并保持可靠使用',('安全','稳定','牢固','防滑','可靠','保护','误服','儿童锁'),'限制误触并提供安全状态反馈','防滑底座、锁扣、独立取药口与状态检测件'),
 ('appearance','获得易辨识且舒适的外观触感',('外观','颜色','好看','质感','材质','做工','颜值'),'通过形态色彩和表面工艺支持辨识握持','圆角壳体、色彩标识与表面纹理'),
 ('service','以可承担成本获得持续维护支持',('价格','客服','物流','安装','售后','性价比'),'控制维护成本并提供故障求助渠道','标准化可更换模块与服务入口'),
 ('power','持续使用并及时了解电量',('电池','充电','续航','电量','耗电'),'管理供电并提示低电量','电池仓、电源管理电路与电量指示组件'),
)
LEGACY_ALIASES={'提醒反馈':'reminder','操作便利':'operation','容量收纳':'storage','安全可靠':'safety','外观质感':'appearance','价格服务':'service'}
NEGATIVE=('不方便','听不清','太小','不清楚','不好','故障','失望','麻烦','没用','坏','漏','困难')
POSITIVE=('方便','满意','清楚','可靠','稳定','够用','喜欢')


def matches(text: str) -> list[tuple]:
    return [r for r in CATALOG if any(w in text.lower() for w in r[2])]


def semantic_mapping(name: str, detail: str='') -> tuple[str,str,str]:
    alias=LEGACY_ALIASES.get(name)
    candidates=[r for r in CATALOG if r[0]==alias or r[1]==name] or matches(name) or matches(detail)
    if not candidates: return '待人工定义产品行为','待人工选择承载组件','缺少可判定语义；待人工审核'
    return candidates[0][3],candidates[0][4],'词典设计推导候选；待专家审核'


def derive_requirements(records: list[dict], topics: dict | None=None, weights: dict | None=None) -> list[dict]:
    weights=weights or dict(frequency=.5,negative_ratio=.3,specificity=.2)
    topic_by_id={r['comment_id']:r for r in (topics or {}).get('assignments',[])}
    groups={r[0]:[] for r in CATALOG}; unknown=[]
    for row in records:
        text=row.get('cleaned_comment',row.get('text',''))
        found=matches(text)
        if not found: unknown.append(row)
        for rule in found: groups[rule[0]].append(row)
    result=[]
    for key,name,terms,function,structure in CATALOG:
        evidence=groups[key]
        if not evidence: continue
        ids=[r['comment_id'] for r in evidence]
        spans=[dict(comment_id=r['comment_id'],text=r.get('cleaned_comment',r.get('text',''))) for r in evidence]
        negatives=sum(any(w in s['text'] for w in NEGATIVE) for s in spans)
        positive=sum(any(w in s['text'] for w in POSITIVE) for s in spans)
        found_terms=sorted({w for w in terms if any(w in s['text'].lower() for s in spans)})
        components=dict(frequency=len(ids)/len(records),negative_ratio=negatives/len(ids),specificity=sum(len(s['text'])>=15 for s in spans)/len(ids))
        tids=sorted({topic_by_id[c]['topic_id'] for c in ids if c in topic_by_id})
        result.append(dict(requirement_id='REQ_'+key,requirement_name=name,requirement_description=f'用户目标：{name}。需要结合评论语境和否定表达人工复核。',
                           source_comment_ids=ids,source_evidence_spans=spans,keywords=found_terms,topic_id=tids,
                           topic_method=(topics or {}).get('actual_algorithm','not_clustered'),sentiment_summary=dict(method='lexicon-indicators-v1',negative=negatives,positive=positive,neutral=len(ids)-len({s['comment_id'] for s in spans if any(w in s['text'] for w in NEGATIVE+POSITIVE)})),
                           frequency=len(ids),importance_score=round(sum(weights[k]*v for k,v in components.items()),10),importance_components=components,importance_weights=weights,
                           derivation_method='versioned-rule-candidate-v2; topic association is descriptive; no automatic human naming',review_status='pending_review',reviewer_note='',catalog_key=key))
    if unknown:
        result.append(dict(requirement_id='REQ_unresolved',requirement_name='待人工审核：尚无明确用户目标',requirement_description='无明确设计诉求或通用好评，不作为正式需求；请人工复核。',source_comment_ids=[r['comment_id'] for r in unknown],source_evidence_spans=[dict(comment_id=r['comment_id'],text=r.get('cleaned_comment',r.get('text',''))) for r in unknown],keywords=[],topic_id=sorted({topic_by_id[r['comment_id']]['topic_id'] for r in unknown if r['comment_id'] in topic_by_id}),topic_method=(topics or {}).get('actual_algorithm','not_clustered'),sentiment_summary={'method':'not_scored'},frequency=len(unknown),importance_score=0.0,importance_components=dict(frequency=0.0,negative_ratio=0.0,specificity=0.0),importance_weights=weights,derivation_method='unresolved_not_requirement',review_status='needs_naming',reviewer_note='',catalog_key='unresolved'))
    return result


def candidate_mappings(requirements: list[dict]) -> list[dict]:
    rows=[]
    for r in requirements:
        if r['review_status']=='needs_naming': continue
        function,structure,method=semantic_mapping(r['requirement_name'])
        rows.append(dict(mapping_id='MAP_'+r['catalog_key'],requirement_id=r['requirement_id'],requirement_name=r['requirement_name'],function_id='FUN_'+r['catalog_key'],function_name=function,structure_id='STR_'+r['catalog_key'],structure_name=structure,
                         source_comment_ids=r['source_comment_ids'],evidence_spans=r['source_evidence_spans'],mapping_reason={'requirement_to_function':f'{function}用于支持用户目标“{r["requirement_name"]}”；证据只支持目标，功能为设计推导。','function_to_structure':f'{structure}是承载“{function}”的候选组件；工程合理性待验证。'},derivation_method=method,confidence=None,review_status='pending_review',reviewer_id='',reviewer_note='',mapping_version='rfs-candidate-v2',knowledge_source='fixed_design_rule: experiment/pipeline/semantics.py CATALOG; no external literature validated',reviewed_at='',review_decision=''))
    return rows
