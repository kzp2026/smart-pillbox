from __future__ import annotations

import math
import statistics
from collections import defaultdict

from v2.research.analysis import REQUIREMENT_LABELS, SENTIMENT_LABELS
from v2.research.dataset import digest


DIMENSIONS = ('需求匹配度', '操作便利性', '结构合理性', '创新性', '工程可行性')


def _labels(value: str, task: str) -> set[str]:
    allowed = set(SENTIMENT_LABELS if task == 'sentiment' else REQUIREMENT_LABELS)
    values = {v.strip() for v in str(value).split('|') if v.strip()}
    if not values or not values <= allowed or (task == 'sentiment' and len(values) != 1):
        raise ValueError(f'{task} 存在空白或非法标签，请按模板填写。')
    if '无明确需求' in values and len(values) != 1:
        raise ValueError('无明确需求不能与其他需求同时出现。')
    return values


def evaluate_predictions(gold: list[dict], predictions: list[dict], valid_ids: set[str]) -> dict:
    truth, tests, seen = {}, defaultdict(dict), set()
    for row in gold:
        cid, task, split = str(row.get('comment_id','')).strip(), row.get('task'), row.get('split')
        key = (task, cid)
        if task not in ('sentiment', 'requirement') or cid not in valid_ids or key in seen:
            raise ValueError('标注包含未知评论、任务或重复 ID；多人标注请先仲裁为一条最终真值。')
        if split not in ('train', 'dev', 'test') or not str(row.get('annotator_id','')).strip():
            raise ValueError('标注必须含匿名标注者 ID 和 train/dev/test 划分。')
        values = _labels(row.get('label',''), task)
        seen.add(key)
        truth[key] = values
        if split == 'test': tests[task][cid] = values
    if gold and not tests:
        raise ValueError('没有独立 test 标注；训练/开发数据不会参与最终评价。')
    groups = defaultdict(dict)
    for row in predictions:
        cid, task = str(row.get('comment_id','')).strip(), row.get('task')
        method = str(row.get('method','')).strip()
        if task not in ('sentiment','requirement') or cid not in valid_ids or not method:
            raise ValueError('预测包含未知评论 ID、任务或空方法名。')
        group = groups[(task, method)]
        if cid in group: raise ValueError('同一方法对同一评论存在重复预测。')
        group[cid] = _labels(row.get('prediction',''), task)
    if not gold:
        return {'metrics': [], 'confusion': [], 'test_ids': {}, 'notes': ['尚无人工标注，不计算准确率/F1。']}
    metrics, confusion, test_ids = [], [], {}
    for task, task_truth in tests.items():
        relevant = [(method, pred) for (t, method), pred in groups.items() if t == task]
        if not relevant: raise ValueError('已有标注但没有对应任务预测。')
        ids = sorted(task_truth)
        test_ids[task] = ids
        allowed = SENTIMENT_LABELS if task == 'sentiment' else REQUIREMENT_LABELS
        for method, pred in relevant:
            if not set(ids) <= set(pred):
                raise ValueError(f'{method} 缺少 test 预测，禁止只挑成功样本比较。')
            tp_sum = fp_sum = fn_sum = 0
            precision, recall, f1 = [], [], []
            for label in allowed:
                tp = sum(label in task_truth[i] and label in pred[i] for i in ids)
                fp = sum(label not in task_truth[i] and label in pred[i] for i in ids)
                fn = sum(label in task_truth[i] and label not in pred[i] for i in ids)
                p, r = tp/(tp+fp) if tp+fp else 0, tp/(tp+fn) if tp+fn else 0
                precision.append(p); recall.append(r); f1.append(2*p*r/(p+r) if p+r else 0)
                tp_sum += tp; fp_sum += fp; fn_sum += fn
            metrics.append(dict(task=task, method=method, n_test=len(ids), test_ids_sha256=digest(ids),
                                accuracy=sum(task_truth[i] == pred[i] for i in ids)/len(ids),
                                macro_precision=statistics.mean(precision), macro_recall=statistics.mean(recall),
                                macro_f1=statistics.mean(f1), micro_f1=2*tp_sum/(2*tp_sum+fp_sum+fn_sum) if 2*tp_sum+fp_sum+fn_sum else 0,
                                present_classes=len(set().union(*task_truth.values()))))
            if task == 'sentiment':
                for actual in allowed:
                    for predicted in allowed:
                        confusion.append(dict(method=method, actual=actual, predicted=predicted,
                                              count=sum(actual in task_truth[i] and predicted in pred[i] for i in ids)))
    return dict(metrics=metrics, confusion=confusion, test_ids=test_ids,
                notes=['macro 指标对固定完整标签集等权平均；无支持类别记 0。',
                       '需求为多标签，Accuracy 是标签集合精确匹配；覆盖率不是准确率。',
                       '仅使用 test 标注；用户须保证未用测试集调参且没有近重复/同源泄漏。',
                       '规则 top1 为固定规则顺序截断消融，不代表其他算法；分数不能自动证明统计显著或创新性。'])


def summarize_reviews(reviews: list[dict], scheme_ids: set[str]) -> list[dict]:
    groups, seen = defaultdict(list), set()
    for row in reviews:
        rid, sid, dimension = (str(row.get(k,'')).strip() for k in ('reviewer_id','scheme_id','dimension'))
        role = str(row.get('role','')).strip()
        if not rid or sid not in scheme_ids or dimension not in DIMENSIONS or role not in ('专家','用户'):
            raise ValueError('评价缺少评审者、有效方案 ID、量表维度或角色（专家/用户）。')
        key = rid, sid, dimension
        if key in seen: raise ValueError('同一评审者对同一方案同一维度重复评分。')
        seen.add(key)
        try: score = float(row['score'])
        except (ValueError, TypeError, KeyError): raise ValueError('评分必须为 1–5 的整数。') from None
        if not math.isfinite(score) or not 1 <= score <= 5 or not score.is_integer():
            raise ValueError('评分必须为 1–5 的整数，不接受空值或无穷大。')
        groups[(sid, dimension, role)].append(score)
    return [dict(scheme_id=sid, dimension=dim, role=role, n=len(scores), mean=statistics.mean(scores),
                 std=statistics.stdev(scores) if len(scores) > 1 else None)
            for (sid, dim, role), scores in sorted(groups.items())]


def readiness(dataset: dict, analysis: dict, evaluation: dict, reviews: list[dict], human_confirmed: bool) -> list[dict]:
    provenance = dataset['card']['provenance']
    missing = [k for k,v in provenance.items() if not v]
    return [
        dict(item='数据来源与抽样', status='已填写，需人工核验' if not missing else '待补充', detail='缺少：'+', '.join(missing) if missing else '信息由提交者填写；不自动认证采集真实性。'),
        dict(item='可复现分析与证据追溯', status='已具备', detail='清洗样本、ID、参数、实际方法、源代码摘要和依赖随实验保存。'),
        dict(item='独立标注与算法对照', status='已计算，需审查实验设计' if evaluation['metrics'] and human_confirmed else '待补充', detail='需真实独立 test 标注、标注规范、仲裁和未用于调参的声明；不自动证明优越性。'),
        dict(item='专家/用户评价', status='已汇总，需审查样本量' if reviews and human_confirmed else '待补充', detail='真实匿名评分按角色与方案分组；单人评分标准差为空，不属于专家共识。'),
        dict(item='论文结论与统计论证', status='需研究者确认', detail='本系统不能保证论文录用；显著性、样本代表性、领域适用性与创新性须另行论证。'),
    ]
