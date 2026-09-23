from __future__ import annotations

import os
from pathlib import Path

from experiment.pipeline.io import sha256,read_json


class AlgorithmUnavailable(RuntimeError):
    pass


def verify_embedding(embedding: dict) -> dict:
    path=Path(embedding['path'])
    if not path.is_absolute():path=Path(__file__).resolve().parents[2]/path
    if not path.is_dir():return {}  # 本地无模型，允许从 HuggingFace 下载
    lock=read_json(Path(__file__).resolve().parents[1]/'models/embedding_manifest.json')
    if embedding['model_id']!=lock['model_id'] or embedding['revision']!=lock['revision']:raise ValueError('嵌入模型ID或revision与方法锁不一致')
    hashes={p.relative_to(path).as_posix():sha256(p) for p in sorted(path.rglob('*')) if p.is_file() and '.cache' not in p.parts}
    if hashes!=lock['files']:raise ValueError('嵌入模型文件哈希不一致；不得继续实验')
    return hashes


def cluster(records: list[dict], config: dict, seed: int) -> dict:
    """Select exactly one implementation. All dependency/model/runtime errors propagate; never switch algorithms."""
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'):
        os.environ.setdefault(key,'1')
    from threadpoolctl import threadpool_limits
    texts=[r.get('cleaned_comment',r.get('text','')) for r in records]
    method=config['algorithm']; features=[]; keywords={}; model_hashes={}
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
        from sklearn.metrics import silhouette_score
        with threadpool_limits(limits=1):
            params=dict(config['tfidf']);params['ngram_range']=tuple(params['ngram_range'])
            matrix=TfidfVectorizer(**params).fit_transform(texts)
            if method=='kmeans_tfidf':
                from sklearn.cluster import KMeans
                vectorizer=TfidfVectorizer(**params);matrix=vectorizer.fit_transform(texts)
                unique_count=len({(tuple(matrix[i].indices),tuple(matrix[i].data)) for i in range(len(texts))})
                if config['n_topics']>unique_count:
                    raise ValueError('指定聚类数超过独立特征向量数量，请明确调整配置')
                model=KMeans(n_clusters=config['n_topics'],random_state=seed,**config['kmeans'])
                labels=model.fit_predict(matrix);features=vectorizer.get_feature_names_out()
                for label in sorted(set(labels)):
                    center=model.cluster_centers_[label]
                    keywords[int(label)]=[str(features[i]) for i in np.argsort(-center,kind='stable')[:10] if center[i]>0]
                actual='KMeans+TF-IDF';metric_matrix=matrix
            elif method=='bertopic':
                embedding=config['embedding'];path=Path(embedding['path'])
                if not path.is_absolute():path=Path(__file__).resolve().parents[2]/path
                model_hashes=verify_embedding(embedding)
                from bertopic import BERTopic
                from sentence_transformers import SentenceTransformer
                from umap import UMAP
                from hdbscan import HDBSCAN
                import torch
                torch.manual_seed(seed);torch.set_num_threads(1)
                model_source=str(path) if path.is_dir() else embedding['model_id']
                encoder=SentenceTransformer(model_source,device=embedding['device'],local_files_only=False,trust_remote_code=False)
                embeddings=encoder.encode(texts,batch_size=embedding['batch_size'],normalize_embeddings=embedding['normalize_embeddings'],show_progress_bar=False,convert_to_numpy=True)
                model=BERTopic(embedding_model=encoder,umap_model=UMAP(random_state=seed,**config['umap']),hdbscan_model=HDBSCAN(**config['hdbscan']),vectorizer_model=CountVectorizer(analyzer='char',ngram_range=(2,3),max_features=3000,min_df=1),**config['bertopic'])
                labels,_=model.fit_transform(texts,embeddings)
                labels=np.asarray(labels)
                for label in sorted(set(labels)):
                    keywords[int(label)]=[str(w) for w,_ in (model.get_topic(int(label)) or [])]
                actual='BERTopic';metric_matrix=embeddings
            else:
                raise ValueError('未知主题算法，必须明确指定 bertopic 或 kmeans_tfidf')
            silhouette=None
            mask=labels!=-1
            if 1<len(set(labels[mask]))<int(mask.sum()):
                silhouette=float(silhouette_score(metric_matrix[mask],labels[mask],metric='cosine',sample_size=min(2000,int(mask.sum())),random_state=seed))
        return dict(actual_algorithm=actual,parameters=config,random_seed=seed,fallback_occurred=False,
                    assignments=[dict(comment_id=r['comment_id'],topic_id=int(label),keywords=keywords[int(label)],topic_method=actual) for r,label in zip(records,labels)],
                    topic_summary=[dict(topic_id=int(label),comment_count=int((labels==label).sum()),keywords=keywords[int(label)],algorithm=actual) for label in sorted(set(labels))],
                    metrics=dict(silhouette_cosine=silhouette,outlier_count=int((labels==-1).sum()),n_clusters=len(set(labels)-{-1})),embedding_file_hashes=model_hashes)
    except AlgorithmUnavailable:
        raise
    except ImportError as exc:
        raise AlgorithmUnavailable(f'{method} 依赖不可用；请安装对应锁定环境，禁止回退') from exc
