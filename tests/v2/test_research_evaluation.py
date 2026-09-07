import importlib.util
import math
import unittest


class ResearchEvaluationTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('v2.research'), '研究评价模块尚未实现')
        from v2.research import evaluation
        return evaluation

    def test_metrics_known_answers_and_no_train_leakage(self):
        ev = self.api()
        gold = [{'comment_id': str(i), 'task':'sentiment', 'label': label, 'split':'test', 'annotator_id':'A'} for i,label in enumerate(['正面','负面','中性'])]
        gold.append({'comment_id':'3','task':'sentiment','label':'正面','split':'train','annotator_id':'A'})
        pred = [{'comment_id':str(i),'task':'sentiment','method':'m','prediction':p} for i,p in enumerate(['正面','负面','正面','负面'])]
        result = ev.evaluate_predictions(gold, pred, {'0','1','2','3'})
        row = result['metrics'][0]
        self.assertEqual(row['n_test'], 3)
        self.assertAlmostEqual(row['accuracy'], 2/3)
        self.assertAlmostEqual(row['macro_f1'], 5/9)
        self.assertEqual(len(result['confusion']), 9)

    def test_invalid_incomplete_and_duplicate_predictions_rejected(self):
        ev = self.api()
        gold = [{'comment_id':'a','task':'sentiment','label':'正面','split':'test','annotator_id':'A'}]
        for pred in [[], [{'comment_id':'a','task':'sentiment','method':'m','prediction':'foo'}], [{'comment_id':'b','task':'sentiment','method':'m','prediction':'正面'}]]:
            with self.assertRaises(ValueError): ev.evaluate_predictions(gold, pred, {'a'})
        with self.assertRaises(ValueError): ev.evaluate_predictions(gold + gold, [], {'a'})

    def test_predictions_are_validated_even_before_human_annotation(self):
        ev=self.api()
        bad=[dict(comment_id='unknown',task='sentiment',method='candidate',prediction='foo')]
        with self.assertRaises(ValueError): ev.evaluate_predictions([],bad,{'a'})
        good=[dict(comment_id='a',task='sentiment',method='candidate',prediction='正面')]
        with self.assertRaises(ValueError): ev.evaluate_predictions([],good+good,{'a'})

    def test_multilabel_and_real_review_validation(self):
        ev = self.api()
        gold = [{'comment_id':'a','task':'requirement','label':'提醒反馈|操作便利','split':'test','annotator_id':'A'}]
        pred = [{'comment_id':'a','task':'requirement','method':'rules','prediction':'提醒反馈'}]
        result = ev.evaluate_predictions(gold, pred, {'a'})
        self.assertEqual(result['metrics'][0]['accuracy'], 0)
        self.assertAlmostEqual(result['metrics'][0]['micro_f1'], 2/3)
        reviews = [{'reviewer_id': r, 'scheme_id':'S1', 'dimension':'需求匹配度', 'score':s, 'role':'专家'} for r,s in [('A',3),('B',5)]]
        stats = ev.summarize_reviews(reviews, {'S1'})
        self.assertEqual(stats[0]['mean'],4)
        self.assertAlmostEqual(stats[0]['std'],math.sqrt(2))
        for bad in [float('nan'),float('inf'),0,6]:
            with self.assertRaises(ValueError): ev.summarize_reviews([dict(reviews[0], score=bad)], {'S1'})
        with self.assertRaises(ValueError): ev.summarize_reviews(reviews + reviews[:1], {'S1'})
        with self.assertRaises(ValueError): ev.summarize_reviews(reviews, {'S2'})
