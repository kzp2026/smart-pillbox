import importlib.util
import tempfile
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest


class ResearchUITests(unittest.TestCase):
    def test_navigation_exposes_paper_center(self):
        from v2.app import NAV_ITEMS
        self.assertIn('论文实验中心',NAV_ITEMS)

    def test_design_navigation_does_not_treat_research_as_a_design(self):
        from v2.app import _cached_runs, _invalidate_view_cache
        from types import SimpleNamespace
        repo=SimpleNamespace(database_url='sqlite:///paper-filter.db',owner_id='owner',schema='agent_v2')
        history=SimpleNamespace(repository=repo,list_runs=lambda *args,**kwargs:[SimpleNamespace(provider='research'),SimpleNamespace(provider='offline')])
        _invalidate_view_cache(repo)
        self.assertEqual([r.provider for r in _cached_runs(history,10)],['offline'])

    def test_empty_view_and_real_run_without_human_data(self):
        self.assertIsNotNone(importlib.util.find_spec('v2.ui.research'),'论文实验页面尚未实现')
        with tempfile.TemporaryDirectory() as directory:
            script = '''
import streamlit as st
import pandas as pd
from pathlib import Path
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.research.dataset import prepare_dataset
from v2.ui.research import render_research
repository=KnowledgeRepository(DATABASE,'tester')
repository.initialize()
store=LocalArtifactStore(Path(STORAGE))
if 'paper_dataset' not in st.session_state:
    st.session_state['paper_dataset']=prepare_dataset(pd.DataFrame({'评论':['声音提醒很好','操作不方便','容量够用','颜色好看']}),b'fixture','test.csv',{'comment':'评论'},{})
render_research(st,repository,store,'测试药盒')
'''.replace('DATABASE',repr(f'sqlite:///{directory}/test.db')).replace('STORAGE',repr(directory+'/files'))
            app=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(app.exception)
            self.assertTrue(any('不自动' in c.value or '不能' in c.value for c in app.warning))
            self.assertTrue(any('legacy' in c.value and '正式' in c.value for c in app.info))
            next(b for b in app.button if b.label=='运行并保存论文实验').click().run(timeout=60)
            self.assertFalse(app.exception)
            self.assertTrue(any('已保存' in s.value for s in app.success))
            self.assertEqual(app.session_state['v2_active_product'],'测试药盒')
            self.assertTrue(any('未提供真实人工' in i.value for i in app.info))
            next(s for s in app.selectbox if s.label=='查看实验结果').set_value('复现与下载').run()
            next(b for b in app.button if b.label=='准备论文报告与完整证据包').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
