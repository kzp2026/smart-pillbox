import hashlib
import importlib.util
import unittest

import pandas as pd


class ResearchDatasetTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('v2.research'), '研究数据模块尚未实现')
        from v2.research.dataset import prepare_dataset
        return prepare_dataset

    def test_counts_ids_metadata_and_redaction(self):
        prepare = self.api()
        df = pd.DataFrame({'评论': [' 很方便 ', '很方便', None, '电话13812345678很清楚', 'x'], '评分': [5, 5, 1, 4, 2]})
        result = prepare(df, b'original', 'input.csv', {'comment': '评论', 'rating': '评分'}, {}, min_length=2)
        self.assertEqual(result['card']['counts'], {'raw': 5, 'empty': 1, 'too_short': 1, 'duplicate': 1, 'valid': 2})
        self.assertEqual(result['card']['input_sha256'], hashlib.sha256(b'original').hexdigest())
        self.assertNotIn('13812345678', str(result['records']))
        self.assertEqual(result['records'][0]['rating'], '5')
        self.assertEqual(result['records'][0]['source_row'], 2)
        self.assertEqual(result['records'][0]['comment_id'], prepare(df.iloc[::-1], b'other', 'x.csv', {'comment':'评论'}, {})['records'][-1]['comment_id'])

    def test_empty_and_missing_mapping_rejected(self):
        prepare = self.api()
        with self.assertRaises(ValueError):
            prepare(pd.DataFrame({'评论':[' ']}), b'x', 'x.csv', {'comment':'评论'}, {})
        with self.assertRaises(ValueError):
            prepare(pd.DataFrame({'评论':['很好']}), b'x', 'x.csv', {'comment':'不存在'}, {})

    def test_analysis_has_explicit_methods_and_evidence(self):
        self.api()
        from v2.research.analysis import analyze
        data = self.api()(pd.DataFrame({'评论':['提醒声音不清楚','容量够用很方便','外观好看','质量不好','提醒很好']}), b'x', 'x.csv', {'comment':'评论'}, {})
        a = analyze(data['records'], seed=42, n_topics=2, use_snownlp=False)
        b = analyze(data['records'], seed=42, n_topics=2, use_snownlp=False)
        self.assertEqual(a['predictions'], b['predictions'])
        self.assertEqual(a['topics'], b['topics'])
        self.assertEqual(a['methods']['topics']['actual'], 'tfidf-char-kmeans')
        self.assertTrue(a['mappings'])
        ids = {r['comment_id'] for r in data['records']}
        self.assertTrue(all(r['comment_id'] in ids for r in a['mappings']))
        self.assertTrue(all(r['method'] != 'BERTopic' for r in a['topics']))
