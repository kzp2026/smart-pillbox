import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment.pipeline.generation import FakeProvider
from experiment.pipeline.io import read_json
from experiment.pipeline.service import run_experiment

ROOT = Path(__file__).resolve().parents[1]


class FinalGuardTests(unittest.TestCase):
    def test_failed_generation_keeps_prompt_parameters_and_error_record(self):
        cfg = read_json(ROOT / 'experiment/config.example.json')
        cfg['generation']['repetitions'] = 1
        cfg['generation']['retry_policy']['max_retries'] = 1
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(FakeProvider, 'generate', side_effect=RuntimeError('private error detail')):
                with self.assertRaises(RuntimeError):
                    run_experiment(cfg, ROOT / 'data/京东智能药盒评论.csv', Path(directory))
            run = next(Path(directory).iterdir())
            manifest = read_json(run / 'run_manifest.json')
            attempts = list(run.glob('stages/generation/*/private/attempts/*.json'))
            self.assertEqual(len(attempts), 1)
            record = read_json(attempts[0])
            self.assertTrue(record['system_prompt'] and record['user_prompt'])
            self.assertEqual(record['parameters'], cfg['generation']['parameters'])
            self.assertEqual(record['retry_count'], 1)
            self.assertEqual(record['status'], 'failed')
            self.assertIn('RuntimeError', record['error'])
            self.assertNotIn('private error detail', json.dumps(record))
            self.assertTrue(manifest['retry_occurred'])
            self.assertTrue(manifest['prompts'])
            self.assertNotIn('evaluation', manifest['stages'])

    def test_annotation_guidelines_contain_candidate_definitions(self):
        from experiment.evaluation.templates import create_templates
        from experiment.pipeline.semantics import derive_requirements
        from openpyxl import load_workbook
        comments = [dict(comment_id='C0001', cleaned_comment='提醒声音太小，听不清')]
        reqs = derive_requirements(comments)
        with tempfile.TemporaryDirectory() as directory:
            create_templates(Path(directory), comments, reqs, [], [])
            ws = load_workbook(Path(directory) / 'annotation_guidelines.xlsx').active
            rows = list(ws.values)
            row = dict(zip(rows[0], rows[1]))
            self.assertEqual(row['name'], reqs[0]['requirement_name'])
            self.assertTrue(row['definition'] and row['exclude'] and row['example'])
            self.assertEqual(row['status'], '候选标注规范，待人工确认')

    def test_comment_column_default_uses_text_not_nickname(self):
        from v2.ui.experiment import default_comment_column_index
        self.assertEqual(default_comment_column_index(['昵称', '评论', '评分']), 1)
        self.assertEqual(default_comment_column_index(['user', 'content']), 1)

    def test_resume_checks_embedding_fingerprint_before_stage(self):
        from experiment.pipeline.service import resume_experiment
        from experiment.pipeline.io import write_json
        cfg = read_json(ROOT / 'experiment/config.example.json')
        with tempfile.TemporaryDirectory() as directory:
            run = run_experiment(cfg, ROOT / 'data/京东智能药盒评论.csv', Path(directory), stop_after='clean')
            manifest = read_json(run / 'run_manifest.json')
            manifest['embedding_file_hashes'] = {'model.safetensors': 'old'}
            write_json(run / 'run_manifest.json', manifest)
            with patch('experiment.pipeline.topics.verify_embedding', return_value={'model.safetensors': 'changed'}):
                with self.assertRaisesRegex(ValueError, '嵌入模型哈希'):
                    resume_experiment(run, cfg, 'topics')


if __name__ == '__main__':
    unittest.main()
