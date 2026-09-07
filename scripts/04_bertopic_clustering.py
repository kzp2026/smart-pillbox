"""Legacy stage compatibility. Formal papers use run_paper_experiment.py."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from common import ensure_output_dir,load_cleaned_or_build,save_workbook
from experiment.pipeline.topics import cluster
from experiment.pipeline.io import write_json


def main():
    parser=argparse.ArgumentParser(description="Legacy 主题阶段：明确算法，失败停止；论文请使用 experiment/run_experiment.py")
    parser.add_argument('--input',default=None)
    parser.add_argument('--output-dir',default='output')
    parser.add_argument('--n-topics',type=int,default=6)
    parser.add_argument('--algorithm',choices=['bertopic','kmeans_tfidf'],default='bertopic',help='默认明确使用 BERTopic；不会回退')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    cfg=json.loads((root/'experiment/config.example.json').read_text(encoding='utf-8'))
    cfg['topic']['algorithm']=args.algorithm;cfg['topic']['n_topics']=args.n_topics
    out=ensure_output_dir(args.output_dir)
    frame=load_cleaned_or_build(args.input,out)
    rows=[dict(comment_id=f'C{i+1:04d}',cleaned_comment=str(text)) for i,text in enumerate(frame['clean_comment'])]
    result=cluster(rows,cfg['topic'],cfg['seed'])
    actual=result['actual_algorithm'];name='BERTopic' if actual=='BERTopic' else 'KMeans_TFIDF'
    detail=pd.DataFrame(result['assignments'])
    summary=pd.DataFrame([dict(topic_id=r['topic_id'],主题名称=f"聚类编号 {r['topic_id']}",评论数=r['comment_count'],主题关键词='、'.join(r['keywords']),algorithm=actual) for r in result['topic_summary']])
    filename='BERTopic主题聚类结果.xlsx' if actual=='BERTopic' else 'KMeans_TFIDF主题聚类结果.xlsx'
    save_workbook(out/filename,{name+'_评论聚类':detail,'主题汇总':summary,'算法说明':pd.DataFrame([{'实际算法':actual,'说明':'显式选择，无回退；legacy兼容输出，正式实验须使用run manifest'}])})
    write_json(out/'topic_method.json',dict(result,legacy=True,output_file=filename))
    print(f'实际使用算法：{actual}；回退：false；输出：{out/filename}')

if __name__=='__main__':main()
