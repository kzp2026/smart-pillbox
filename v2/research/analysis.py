from __future__ import annotations

import re
from collections import Counter

from experiment.pipeline.semantics import CATALOG, LEGACY_ALIASES, candidate_mappings, derive_requirements


_CATALOG_BY_KEY = {key: row for key, *rest in CATALOG for row in [(key, *rest)]}
# Historical labels remain an input/output compatibility view over the shared catalog.
RULES = {label: _CATALOG_BY_KEY[key][2] for label, key in LEGACY_ALIASES.items()}
SENTIMENT_LABELS = ('负面', '中性', '正面')
REQUIREMENT_LABELS = tuple(RULES) + ('无明确需求',)
POSITIVE = ('好', '方便', '满意', '清楚', '可靠', '稳定', '够用', '喜欢')
NEGATIVE = ('差', '坏', '麻烦', '失望', '故障', '漏', '困难', '噪音')


def sentiment_rule(text: str, negation: bool) -> str:
    score = 0
    for word, weight in [(w, 1) for w in POSITIVE] + [(w, -1) for w in NEGATIVE]:
        for match in re.finditer(re.escape(word), text):
            prefix = text[max(0, match.start()-3):match.start()]
            score += -weight if negation and re.search(r'(不|没|未|无|非|别).{0,1}$', prefix) else weight
    return '正面' if score > 0 else '负面' if score < 0 else '中性'


def analyze(records: list[dict], seed: int = 42, n_topics: int = 6,
            use_snownlp: bool = True) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import silhouette_score

    if not records or not 1 <= n_topics <= 30 or not 0 <= seed <= 2**32-1:
        raise ValueError('实验参数无效：主题数 1–30，随机种子 0–4294967295，且需要有效评论。')
    texts = [r['text'] for r in records]
    predictions, mappings = [], []
    snow = None
    methods = {
        'sentiment': {'actual': ['lexicon-v1', 'lexicon-negation-v1'], 'fallback': None},
        'requirements': {'actual': ['rules-all-v1', 'rules-top1-v1'], 'fallback': None},
        'topics': {'actual': 'tfidf-char-kmeans', 'requested_k': n_topics, 'fallback': None},
        'snow': {'requested': use_snownlp, 'actual': None, 'status': 'not_requested'},
    }
    if use_snownlp:
        try:
            from snownlp import SnowNLP
            snow = SnowNLP
        except ImportError:
            methods['snow']['status'] = 'unavailable_dependency'
        else:
            methods['snow'].update(actual='SnowNLP pretrained', status='completed')
    snow_predictions = []
    for record in records:
        cid, text = record['comment_id'], record['text']
        for method, neg in [('lexicon-v1', False), ('lexicon-negation-v1', True)]:
            predictions.append(dict(comment_id=cid, task='sentiment', method=method, prediction=sentiment_rule(text, neg)))
        if snow:
            try:
                score = float(snow(text).sentiments)
                snow_predictions.append(dict(comment_id=cid, task='sentiment', method='snownlp-pretrained',
                                             prediction='正面' if score >= .6 else '负面' if score <= .4 else '中性'))
            except Exception:
                # Do not mix partial SnowNLP predictions with rules under one method name.
                methods['snow'].update(actual=None, status='failed_no_fallback')
                snow = None
                snow_predictions = []
        labels = [label for label, keys in RULES.items() if any(k in text for k in keys)] or ['无明确需求']
        for method, values in [('rules-all-v1', labels), ('rules-top1-v1', labels[:1])]:
            predictions.append(dict(comment_id=cid, task='requirement', method=method, prediction='|'.join(values)))
        shared = derive_requirements([dict(comment_id=cid, cleaned_comment=text)])
        shared_by_key = {row['catalog_key']: row for row in shared}
        for label in labels:
            key = LEGACY_ALIASES.get(label)
            if not key or key not in shared_by_key:
                continue
            row = candidate_mappings([shared_by_key[key]])[0]
            mappings.append(dict(comment_id=cid, requirement=label,
                                 function=row['function_name'], structure=row['structure_name'],
                                 evidence=text, source=row['derivation_method'], review_status='pending_review'))
    predictions.extend(snow_predictions)
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3), max_features=3000, min_df=1)
    topics, keywords = [], []
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        methods['topics'].update(status='unavailable_empty_vocabulary', effective_k=0, silhouette=None)
    else:
        features = vectorizer.get_feature_names_out()
        weights = matrix.mean(axis=0).A1
        keywords = [{'keyword': str(features[i]), 'weight': float(weights[i])}
                    for i in weights.argsort()[::-1][:30]]
        # Bound by distinct feature rows, not merely the number of documents.
        unique_count = len({(tuple(matrix[i].indices), tuple(matrix[i].data)) for i in range(matrix.shape[0])})
        k = min(n_topics, len(texts), unique_count)
        labels = KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(matrix)
        silhouette = None
        if 1 < len(set(labels)) < len(texts):
            silhouette = float(silhouette_score(matrix, labels, metric='cosine', sample_size=min(2000, len(texts)), random_state=seed))
        methods['topics'].update(status='completed', effective_k=len(set(labels)), silhouette=silhouette,
                                 vectorizer={'analyzer':'char', 'ngram_range':[2,3], 'max_features':3000, 'min_df':1},
                                 seed=seed, n_init=10)
        topic_terms = {}
        for label in set(labels):
            centroid = matrix[labels == label].mean(axis=0).A1
            topic_terms[int(label)] = ' | '.join(str(features[i]) for i in centroid.argsort()[::-1][:6] if centroid[i] > 0)
        for cid, label in zip((r['comment_id'] for r in records), labels):
            topics.append(dict(comment_id=cid, topic=int(label), keywords=topic_terms[int(label)], method='tfidf-char-kmeans'))
    counts = Counter(r['requirement'] for r in mappings)
    coverage = len({r['comment_id'] for r in mappings}) / len(records)
    return dict(predictions=predictions, mappings=mappings, topics=topics, keywords=keywords, methods=methods,
                requirement_counts=dict(counts), evidence_coverage=coverage)
