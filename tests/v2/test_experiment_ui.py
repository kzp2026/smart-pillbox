import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from v2.application.experiment import ExperimentService


class ExperimentUITests(unittest.TestCase):
    def test_reopen_immediately_shows_status_and_download(self):
        script = '''
import streamlit as st
from types import SimpleNamespace
from v2.ui.experiment import render_experiment
row=SimpleNamespace(id='RUN_FIXTURE',model='paper-repro-v2.1',created_at='2026-09-06')
repo=SimpleNamespace(list_pipeline_runs=lambda *args,**kwargs:[row])
render_experiment(st,repo,object(),'测试药盒')
'''
        result = dict(product='测试药盒', method_version='paper-repro-v2.1', actual_algorithm='KMeans+TF-IDF',
                      evidence_count=1, approved_mapping_count=0, generation_mode='fake',
                      independent_evaluation_completed=False, closed_loop_validated=False)
        with patch.object(ExperimentService, 'load', return_value=result):
            app=AppTest.from_string(script).run(timeout=15)
            next(button for button in app.button if button.label=='重新打开正式复现实验').click().run(timeout=15)
        self.assertFalse(app.exception)
        self.assertTrue(any(button.label=='准备完整复现运行 ZIP' for button in app.button))
        self.assertEqual(app.session_state['v2_active_product'],'测试药盒')

    def test_research_mode_requires_explicit_paid_call_authorization(self):
        script = '''
import streamlit as st
from types import SimpleNamespace
from v2.ui.experiment import render_experiment
repo=SimpleNamespace(list_pipeline_runs=lambda *args,**kwargs:[])
render_experiment(st,repo,object(),'测试药盒')
'''
        app = AppTest.from_string(script).run(timeout=15)
        self.assertFalse(app.exception)
        self.assertTrue(any(item.label == '运行模式' for item in app.selectbox))
        mode = next(item for item in app.selectbox if item.label == '运行模式')
        mode.select('research').run()
        self.assertTrue(any(button.label == '准备研究材料（停在图谱）' for button in app.button))
        self.assertFalse(any('运行真实生成' in button.label for button in app.button))


if __name__=='__main__':unittest.main()
