"""Explicit paired algorithm execution; neither method substitutes for the other."""
import argparse
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from experiment.pipeline.io import write_json,read_json
from experiment.pipeline.service import run_experiment,artifact,read_manifest


def compare(config,input_path,runs_root):
    from sklearn.metrics import adjusted_rand_score,normalized_mutual_info_score
    results={};runs={}
    for algorithm in ('kmeans_tfidf','bertopic'):
        cfg=copy.deepcopy(config);cfg['topic']['algorithm']=algorithm
        run=run_experiment(cfg,input_path,runs_root)
        runs[algorithm]=str(run.resolve())
        results[algorithm]=read_json(artifact(run,'topics','topics.json'))
    a,b=results['kmeans_tfidf'],results['bertopic']
    if [r['comment_id'] for r in a['assignments']]!=[r['comment_id'] for r in b['assignments']]:raise ValueError('方法比较的评论ID不一致')
    report={'runs':runs,'metrics':{k:v['metrics'] for k,v in results.items()},'adjusted_rand':float(adjusted_rand_score([r['topic_id'] for r in a['assignments']],[r['topic_id'] for r in b['assignments']])),'normalized_mutual_information':float(normalized_mutual_info_score([r['topic_id'] for r in a['assignments']],[r['topic_id'] for r in b['assignments']])),'interpretation':'主题数、离群率和跨算法一致性是描述性指标；不同表示空间的silhouette不可直接当作优劣证明；无人工主题真值不计算准确率。'}
    output=Path(runs_root)/('comparison_'+read_manifest(Path(runs['bertopic']))['run_id']+'.json')
    write_json(output,report);return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--runs-root',type=Path,default=Path('experiment/runs'))
    a=p.parse_args();print(compare(read_json(a.config),a.input,a.runs_root))
