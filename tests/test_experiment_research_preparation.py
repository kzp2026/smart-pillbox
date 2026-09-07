import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from experiment.pipeline.generation import generate_groups


class ResearchPreparationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(Path('experiment/config.example.json').read_text(encoding='utf-8'))
        self.cfg['generation']['repetitions'] = 1
        self.graph = {'used_graph_paths': [], 'evidence_status': '无正式图谱证据', 'simulated': False}

    def test_abc_common_constraints_and_task_are_identical(self):
        records, _, _ = generate_groups('test', self.cfg, [], [], self.graph)
        inputs = {r['group']: json.loads(r['user_prompt']) for r in records}
        for field in ('industrial_constraints', 'ordinary_requirements', 'task', 'output_format'):
            self.assertEqual(inputs['A'][field], inputs['B'][field])
            self.assertEqual(inputs['B'][field], inputs['C'][field])
        self.assertEqual(inputs['A']['industrial_constraints'], self.cfg['industrial_constraints'])
        self.assertIn('input_lengths', records[0])

    def test_research_c_without_review_stops_before_any_request(self):
        self.cfg['generation'].update(mode='research', provider='deepseek', model='deepseek-chat')
        provider = Mock(mode='live')
        with self.assertRaisesRegex(ValueError, '审核'):
            generate_groups('formal', self.cfg, [], [], self.graph, provider=provider)
        provider.generate.assert_not_called()

    def test_strict_provider_actual_request_contains_paths_and_metadata(self):
        from experiment.pipeline.providers import ResearchTextProvider
        client = Mock()
        client.create.return_value = {'id': 'response-test', 'model': 'reported-model',
            'choices': [{'message': {'content': 'test design'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 91, 'completion_tokens': 4, 'total_tokens': 95}}
        from v2.providers.text import DeepSeekTextProvider
        provider = ResearchTextProvider(DeepSeekTextProvider('test-only', completion_client=client),
                                        allow_paid=True, transport_is_mock=True)
        prompt = json.dumps({'used_graph_paths': [{'comment_id': 'C0001'}]})
        response = provider.generate('system', prompt, self.cfg['generation']['parameters'])
        self.assertEqual(client.create.call_args.kwargs['messages'][1]['content'], prompt)
        self.assertEqual(response['text'], 'test design')
        self.assertEqual(response['usage']['prompt_tokens'], 91)
        self.assertNotIn('seed', client.create.call_args.kwargs)
        self.assertEqual(response['model_version'], 'unknown')

    def test_strict_failure_never_returns_fallback(self):
        from experiment.pipeline.providers import ResearchTextProvider
        from v2.providers.text import DeepSeekTextProvider
        client = Mock(); client.create.side_effect = RuntimeError('sk-do-not-log-me')
        provider = ResearchTextProvider(DeepSeekTextProvider('test-only', completion_client=client),
                                        allow_paid=True, transport_is_mock=True)
        with self.assertRaises(RuntimeError):
            provider.generate('system', '{}', self.cfg['generation']['parameters'])

    def test_paid_call_requires_runtime_authorization(self):
        from experiment.pipeline.providers import ResearchTextProvider
        from v2.providers.text import DeepSeekTextProvider
        client = Mock()
        provider = ResearchTextProvider(DeepSeekTextProvider('test-only', completion_client=client))
        with self.assertRaisesRegex(ValueError, '费用授权'):
            provider.generate('system', '{}', self.cfg['generation']['parameters'])
        client.create.assert_not_called()

    def test_removing_topics_changes_only_descriptive_association(self):
        from experiment.pipeline.semantics import derive_requirements, candidate_mappings
        comments=[{'comment_id':'C0001','cleaned_comment':'提醒声音太小，老人操作不方便'}]
        with_topics=derive_requirements(comments,{'actual_algorithm':'BERTopic','assignments':[{'comment_id':'C0001','topic_id':2}]})
        without_topics=derive_requirements(comments)
        self.assertEqual(candidate_mappings(with_topics),candidate_mappings(without_topics))
        for a,b in zip(with_topics,without_topics):
            self.assertEqual({k:v for k,v in a.items() if k not in ('topic_id','topic_method')},
                             {k:v for k,v in b.items() if k not in ('topic_id','topic_method')})

    def test_self_declared_live_provider_is_not_formal_evidence(self):
        self.cfg['generation'].update(mode='research',provider='deepseek',model='deepseek-chat',groups=['A'])
        provider=Mock(mode='live',transport_is_mock=False)
        provider.generate.return_value='fabricated live'
        with self.assertRaisesRegex(ValueError,'严格|真实provider'):
            generate_groups('research',self.cfg,[],[],self.graph,provider=provider)
        provider.generate.assert_not_called()

    def test_test_mode_cannot_use_live_transport(self):
        provider=Mock(mode='live',transport_is_mock=False)
        with self.assertRaisesRegex(ValueError,'测试'):
            generate_groups('test',self.cfg,[],[],self.graph,provider=provider)
        provider.generate.assert_not_called()

    def test_actual_backend_model_must_equal_config(self):
        from experiment.pipeline.providers import ResearchTextProvider
        from v2.providers.text import DeepSeekTextProvider
        self.cfg['simulated']=True
        self.cfg['generation'].update(mode='transport_test',provider='deepseek',model='requested-model')
        client=Mock()
        provider=ResearchTextProvider(DeepSeekTextProvider('TEST_ONLY',model='wrong-model',completion_client=client),allow_paid=True,transport_is_mock=True)
        with self.assertRaisesRegex(ValueError,'模型与实验配置'):
            generate_groups('test',self.cfg,[],[],self.graph,provider=provider)
        client.create.assert_not_called()

    def test_failed_revision_does_not_retain_parent_api_response(self):
        from experiment.pipeline.generation import _invoke,FakeProvider
        record={'system_prompt':'system','user_prompt':'{}','parameters':{},'retry_policy':{'max_retries':0},
                'retry_count':0,'is_real_ai':True,'raw_api_response':{'id':'old-response'}}
        provider=FakeProvider()
        with unittest.mock.patch.object(provider,'generate',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):_invoke(provider,record)
        self.assertFalse(record['is_real_ai']);self.assertIsNone(record['raw_api_response'])


if __name__ == '__main__':
    unittest.main()
