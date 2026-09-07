"""Legacy Excel projection of the authoritative candidate mappings; not an expert-reviewed graph."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from common import ensure_output_dir,save_workbook
from experiment.pipeline.semantics import derive_requirements,candidate_mappings
from experiment.pipeline.io import table,write_json


def main():
    parser=argparse.ArgumentParser(description='Legacy需求映射投影；论文权威入口为 experiment/run_experiment.py')
    parser.add_argument('--output-dir',default='output');parser.add_argument('--product-name',default='产品')
    args=parser.parse_args();out=ensure_output_dir(args.output_dir)
    cleaned=out/'cleaned_comments.xlsx'
    if not cleaned.exists():raise FileNotFoundError('指定目录缺少 cleaned_comments.xlsx；禁止从其他目录补读')
    frame=pd.read_excel(cleaned)
    rows=[dict(comment_id=f'C{i+1:04d}',cleaned_comment=str(t)) for i,t in enumerate(frame['clean_comment'])]
    topic_path=out/'topic_method.json'
    if not topic_path.exists():raise FileNotFoundError('请先在同目录完成明确算法的04阶段，不能读取legacy主题文件代替')
    topics=json.loads(topic_path.read_text(encoding='utf-8'))
    reqs=derive_requirements(rows,topics);mappings=candidate_mappings(reqs)
    def projected(items):
        return pd.DataFrame([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in items])
    req_rows=[dict(r,req_id=r['requirement_id'],需求名称=r['requirement_name'],需求类别=r['catalog_key'],需求描述=r['requirement_description'],来源关键词='、'.join(r['keywords']),重要度=r['importance_score']) for r in reqs]
    save_workbook(out/f'{args.product_name}_需求功能映射数据库.xlsx',{
        '用户需求表':projected(req_rows),
        '产品功能表':projected([dict(func_id=r['function_id'],功能名称=r['function_name'],review_status='pending_review') for r in mappings]),
        '产品结构表':projected([dict(structure_id=r['structure_id'],结构名称=r['structure_name'],review_status='pending_review') for r in mappings]),
        '需求功能映射':projected([dict(req_id=r['requirement_id'],func_id=r['function_id'],映射理由=r['mapping_reason']['requirement_to_function'],review_status='pending_review',source_comment_ids=r['source_comment_ids']) for r in mappings]),
        '功能结构映射':projected([dict(func_id=r['function_id'],structure_id=r['structure_id'],映射理由=r['mapping_reason']['function_to_structure'],review_status='pending_review') for r in mappings]),
        '主题需求映射':pd.DataFrame(columns=['topic_id','req_id','映射依据']),
        '设计机会点':projected([dict(设计机会点=r['requirement_name'],建议功能=r['function_name'],建议结构=r['structure_name'],论文实验解释='规则设计推导候选，未经过专家审核') for r in mappings]),
        '研究边界':pd.DataFrame([{'状态':'legacy兼容投影','说明':'不是正式图谱；仅experiment/run_experiment.py的approved关系可作为图谱驱动证据'}])})
    write_json(out/'legacy_mapping_candidates.json',mappings)
    print(f'共享规则需求候选：{len(reqs)}；映射候选：{len(mappings)}；正式审核关系：0')

if __name__=='__main__':main()
