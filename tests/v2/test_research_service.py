import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore


class ResearchServiceTests(unittest.TestCase):
    def test_external_candidate_is_compared_and_incomplete_predictions_fail(self):
        from v2.application.research import ResearchService
        from v2.research.dataset import prepare_dataset
        with tempfile.TemporaryDirectory() as directory:
            repo=KnowledgeRepository(f'sqlite:///{directory}/test.db','owner'); repo.initialize()
            service=ResearchService(repo,LocalArtifactStore(Path(directory)/'files'))
            dataset=prepare_dataset(pd.DataFrame({'评论':['提醒不好','使用方便']}),b'x','x.csv',{'comment':'评论'},{})
            ids=[r['comment_id'] for r in dataset['records']]
            gold=[dict(comment_id=i,task='sentiment',label=l,split='test',annotator_id='synthetic-test-only') for i,l in zip(ids,['负面','正面'])]
            pred=[dict(comment_id=i,task='sentiment',method='candidate-test-fixture',prediction=l) for i,l in zip(ids,['负面','正面'])]
            self.assertIn('external_predictions',__import__('inspect').signature(service.run).parameters)
            result=service.run('测试',dataset,dict(seed=42,n_topics=2,use_snownlp=False),gold=gold,human_confirmed=True,
                               external_predictions=pred,method_notes='Synthetic test fixture; not research evidence.')
            self.assertEqual(next(r for r in result['evaluation']['metrics'] if r['method']=='candidate-test-fixture')['accuracy'],1)
            with self.assertRaises(ValueError):
                service.run('测试',dataset,dict(seed=42,n_topics=2,use_snownlp=False),gold=gold,human_confirmed=True,
                            external_predictions=pred[:1],method_notes='fixture')

    def test_archive_reopen_reproduce_and_honest_report(self):
        self.assertIsNotNone(importlib.util.find_spec('v2.application.research'), '持久化实验服务尚未实现')
        from v2.application.research import ResearchService
        from v2.research.dataset import prepare_dataset
        with tempfile.TemporaryDirectory() as directory:
            repo = KnowledgeRepository(f'sqlite:///{directory}/test.db', 'owner')
            repo.initialize()
            store = LocalArtifactStore(Path(directory)/'files')
            dataset = prepare_dataset(pd.DataFrame({'评论':['提醒声音不好','操作方便','容量够用','颜色不错']}), b'input', 'x.csv', {'comment':'评论'}, {})
            result = ResearchService(repo,store).run('药盒', dataset, {'seed':42,'n_topics':2,'use_snownlp':False}, nonce='once')
            again = ResearchService(repo,store).run('药盒', dataset, {'seed':42,'n_topics':2,'use_snownlp':False}, nonce='once')
            self.assertEqual(result['manifest']['run_id'], again['manifest']['run_id'])
            self.assertEqual(repo.count_rows('pipeline_runs'),1)
            loaded = ResearchService(repo,store).load(result['manifest']['run_id'])
            self.assertEqual(loaded, result)
            self.assertFalse(result['evaluation']['metrics'])
            self.assertTrue(any(r['status']=='待补充' for r in result['readiness']))
            zipped = ResearchService(repo,store).download(result['manifest']['run_id'])
            with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
                files = set(archive.namelist())
                for expected in ('experiment.json','manifest.json','论文实验报告.docx','report.md','predictions.csv','annotation_template.csv','requirements.csv','charts.png'):
                    self.assertIn(expected, files)
                self.assertIn('source/v2/research/reproduce.py',files)
                self.assertIn('source/v2/application/imports.py',files)
                manifest = json.loads(archive.read('manifest.json'))
                for name,sha in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), sha)
                self.assertIn('不能证明',archive.read('report.md').decode('utf-8'))
            replay = ResearchService(repo,store).replay(result['manifest']['run_id'])
            self.assertEqual(replay['analysis']['predictions'],result['analysis']['predictions'])
            self.assertNotEqual(replay['manifest']['run_id'],result['manifest']['run_id'])
