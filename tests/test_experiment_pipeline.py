import copy
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def api(self):
        self.assertTrue((ROOT/'experiment/pipeline/service.py').exists(), '缺少权威论文实验服务层')
        return importlib.import_module('experiment.pipeline.service')

    def config(self):
        self.api()
        return json.loads((ROOT/'experiment/config.example.json').read_text(encoding='utf-8'))

    def run_case(self, root, **kwargs):
        cfg = self.config()
        cfg['generation']['repetitions'] = 1
        return self.api().run_experiment(cfg, ROOT/'data/京东智能药盒评论.csv', Path(root), **kwargs)

    def test_01_authoritative_service_exists(self):
        self.api()

    def test_clean_510_audit_conservation_and_no_nicknames(self):
        self.api()
        from experiment.pipeline.cleaning import clean_input
        rows, audit, counts = clean_input(ROOT/'data/京东智能药盒评论.csv', self.config()['cleaning'])
        self.assertEqual(counts['raw'], 510)
        self.assertEqual(counts['valid'], 500)
        self.assertEqual(counts['duplicate'], 10)
        self.assertEqual(len(audit), 510)
        self.assertEqual(len({r['comment_id'] for r in audit}), 510)
        self.assertTrue(all(r['duplicate_of'] in {x['comment_id'] for x in rows} for r in audit if r['result']=='merged_duplicate'))
        self.assertNotIn('昵称', str(rows))

    def test_independent_runs_deterministic_non_ai(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.run_case(d), self.run_case(d)
            self.assertNotEqual(a, b)
            ma, mb = self.api().read_manifest(a), self.api().read_manifest(b)
            for stage in ('clean','topics','requirements','mapping','graph'):
                ja = {Path(k).name:v for k,v in ma['stages'][stage]['outputs'].items() if k.endswith('.json')}
                jb = {Path(k).name:v for k,v in mb['stages'][stage]['outputs'].items() if k.endswith('.json')}
                self.assertEqual(ja, jb, stage)

    def test_manifest_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            run = self.run_case(d); m = self.api().read_manifest(run)
            fields = ('run_id','started_at','finished_at','git_commit','workspace_dirty','python','operating_system','dependencies','input_path','input_sha256','counts','actual_algorithm','algorithm_parameters','random_seed','stages','provider','model','generation_parameters','prompts','retry_occurred','fallback_occurred','error_summary','artifacts','importance_formula','config_sha256')
            self.assertTrue(all(f in m for f in fields))
            self.assertFalse(m['fallback_occurred'])
            self.assertEqual(m['input_sha256'], hashlib.sha256((ROOT/'data/京东智能药盒评论.csv').read_bytes()).hexdigest())
            for s in m['stages'].values():
                self.assertEqual(s['status'],'completed')
                for p,h in {**s['inputs'], **s['outputs']}.items():
                    self.assertEqual(hashlib.sha256((run/p).read_bytes()).hexdigest(),h,p)

    def test_never_reads_other_run_latest_file(self):
        with tempfile.TemporaryDirectory() as d:
            evil=Path(d)/'other'; evil.mkdir(); (evil/'requirements.json').write_text('POISON')
            run=self.run_case(d)
            self.assertNotIn('POISON',self.api().artifact(run,'requirements','requirements.json').read_text(encoding='utf-8'))

    def test_requirements_mapping_evidence_and_semantics(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d)
            req=json.loads(self.api().artifact(run,'requirements','requirements.json').read_text(encoding='utf-8'))
            mappings=json.loads(self.api().artifact(run,'mapping','mappings.json').read_text(encoding='utf-8'))
            self.assertTrue(req); self.assertTrue(mappings)
            for r in req:
                self.assertTrue(r['source_comment_ids']); self.assertTrue(r['source_evidence_spans'])
                self.assertNotRegex(r['requirement_name'],r'^主题\d+$')
                self.assertTrue(0 <= r['importance_score'] <= 1)
            for row in mappings:
                self.assertTrue(row['requirement_id']); self.assertTrue(row['evidence_spans']); self.assertTrue(row['mapping_reason'])
                self.assertEqual(row['review_status'],'pending_review')
                self.assertNotRegex(str(row),r'主题\d+(优化功能|支撑结构)')

    def test_no_approved_paths_without_humans(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d)
            graph=json.loads(self.api().artifact(run,'graph','graph.json').read_text(encoding='utf-8'))
            self.assertEqual(graph['used_graph_paths'],[])
            self.assertEqual(graph['evidence_status'],'无正式图谱证据')

    def test_unavailable_algorithm_stops_and_records_failure(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=self.config(); cfg['topic']['algorithm']='bertopic'
            cfg['topic']['embedding']['path']='missing-model-for-test'
            with self.assertRaises(Exception):
                self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d))
            m=self.api().read_manifest(next(Path(d).iterdir()))
            self.assertEqual(m['status'],'failed'); self.assertFalse(m['fallback_occurred'])
            self.assertEqual(m['stages']['topics']['status'],'failed')
            self.assertNotIn('requirements',m['stages'])

    def test_algorithm_names_match_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d); m=self.api().read_manifest(run)
            self.assertEqual(m['actual_algorithm'],'KMeans+TF-IDF')
            self.assertTrue(any('KMeans_TFIDF' in p for p in m['stages']['topics']['outputs']))
            self.assertFalse(any('BERTopic' in p for p in m['stages']['topics']['outputs']))

    def test_resume_rejects_upstream_tampering_and_config_changes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=self.config(); cfg['generation']['repetitions']=1
            run=self.run_case(d)
            changed=copy.deepcopy(cfg); changed['seed']=17
            with self.assertRaisesRegex(ValueError,'配置'):
                self.api().resume_experiment(run,changed,'generation')
            self.api().artifact(run,'clean','comments.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'哈希'):
                self.api().resume_experiment(run,cfg,'generation')

    def test_valid_resume_keeps_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d); m=self.api().read_manifest(run)
            old={p:(run/p).read_bytes() for p in m['artifacts']}
            cfg=self.config();cfg['generation']['repetitions']=1
            self.api().resume_experiment(run,cfg,'generation')
            self.assertTrue(all((run/p).read_bytes()==data for p,data in old.items()))

    def test_generation_records_and_blind_control(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d)
            records=json.loads(self.api().artifact(run,'generation','generation_records.json').read_text(encoding='utf-8'))
            self.assertEqual({r['group'] for r in records},{'A','B','C'})
            controls=[{k:r[k] for k in ('model','provider','parameters','task','output_format','image_count','retry_policy')} for r in records]
            self.assertTrue(all(c==controls[0] for c in controls))
            for r in records:
                self.assertTrue(r['system_prompt']);self.assertTrue(r['user_prompt']);self.assertIn('used_graph_paths',r)
                self.assertEqual(r['mode'],'fake');self.assertFalse(r['is_real_ai'])
                self.assertEqual(r['response_sha256'],hashlib.sha256(r['raw_response'].encode()).hexdigest())
            blind=json.loads(self.api().artifact(run,'generation','blind_schemes.json').read_text(encoding='utf-8'))
            self.assertEqual(len(blind),3)
            self.assertTrue(all(set(r)=={'scheme_id','content'} for r in blind))

    def test_no_quality_or_significance_claims(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d)
            check=json.loads(self.api().artifact(run,'report','completeness.json').read_text(encoding='utf-8'))
            self.assertEqual(check['kind'],'流程完整度检查')
            self.assertFalse(check['independent_evaluation_completed'])
            self.assertNotIn('quality_score',check)
            self.assertFalse(check['v1_v2_loop_completed'])

    def test_reject_secret_and_paid_provider_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=self.config();cfg['generation']['api_key']='secret-test-value'
            with self.assertRaises(ValueError):
                self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d))

    def test_reviewed_paths_are_in_actual_prompt_and_reconstruct(self):
        with tempfile.TemporaryDirectory() as d:
            run=self.run_case(d)
            rows=json.loads(self.api().artifact(run,'mapping','mappings.json').read_text(encoding='utf-8'))
            row=rows[0];row.update(review_status='approved',reviewer_id='SIM_REVIEWER01',reviewer_note='模拟fixture审核，不是专家证据')
            review=Path(d)/'sim_review.json';review.write_text(json.dumps([row],ensure_ascii=False),encoding='utf-8')
            cfg=self.config();cfg['simulated']=True;cfg['generation']['repetitions']=1
            child=self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d),mapping_review=review)
            graph=json.loads(self.api().artifact(child,'graph','graph.json').read_text(encoding='utf-8'))
            from experiment.pipeline.graph import reconstruct
            self.assertTrue(reconstruct(graph['nodes'],graph['edges']))
            records=json.loads(self.api().artifact(child,'generation','generation_records.json').read_text(encoding='utf-8'))
            c=next(r for r in records if r['group']=='C')
            self.assertTrue(c['used_graph_paths'])
            self.assertEqual(json.loads(c['user_prompt'])['used_graph_paths'],c['used_graph_paths'])
            self.assertTrue(all(p['comment_id'] in c['used_comment_ids'] for p in c['used_graph_paths']))
            evaluated=self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d),parent_run=child)
            eg=json.loads(self.api().artifact(evaluated,'graph','graph.json').read_text(encoding='utf-8'))
            self.assertEqual(eg['used_graph_paths'],graph['used_graph_paths'])
            self.assertEqual(eg['approved_mapping_count'],graph['approved_mapping_count'])

    def test_v1_v2_revision_then_second_evaluation_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=self.config();cfg['simulated']=True;cfg['generation']['repetitions']=1
            parent=self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d))
            records=json.loads(self.api().artifact(parent,'generation','generation_records.json').read_text(encoding='utf-8'))
            original=next(r for r in records if r['group']=='C')
            mapping=json.loads(self.api().artifact(parent,'mapping','mappings.json').read_text(encoding='utf-8'))[0]
            from experiment.evaluation.statistics import DIMENSIONS
            review=dict(reviewer_id='SIM_R01',background='模拟工业设计',scheme_id=original['scheme_id'],evaluated_at='2026-09-05T00:00:00Z',strengths='模拟优点',issues='模拟：操作反馈不清楚',suggestions='模拟：增大确认按键',**{dim:2 for dim in DIMENSIONS})
            rv=Path(d)/'reviews.json';rv.write_text(json.dumps([review],ensure_ascii=False),encoding='utf-8')
            change=dict(change_id='CH01',v1_scheme_id=original['scheme_id'],v2_scheme_id='SIM_SCHEME_V2',reviewer_id='SIM_R01',low_dimension='操作便利性',expert_issue=review['issues'],requirement_id=mapping['requirement_id'],function_id=mapping['function_id'],structure_id=mapping['structure_id'],prompt_field='controls',old_value=json.loads(original['user_prompt'])['controls'],new_value='模拟修改：增大确认按键并增加明确状态反馈',reason='模拟低分项修改')
            ch=Path(d)/'changes.json';ch.write_text(json.dumps([change],ensure_ascii=False),encoding='utf-8')
            revised=self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d),parent_run=parent,reviews=rv,changes=ch)
            newrecords=json.loads(self.api().artifact(revised,'generation','generation_records.json').read_text(encoding='utf-8'))
            v2=next(r for r in newrecords if r['scheme_id']=='SIM_SCHEME_V2')
            self.assertEqual(v2['result_version'],'V2')
            self.assertIn(change['new_value'],v2['user_prompt'])
            second={**review,'scheme_id':'SIM_SCHEME_V2',**{dim:4 for dim in DIMENSIONS}}
            rv2=Path(d)/'reviews_v2.json';rv2.write_text(json.dumps([second],ensure_ascii=False),encoding='utf-8')
            final=self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d),parent_run=revised,reviews=rv2)
            stats=json.loads(self.api().artifact(final,'evaluation','v1_v2_comparison.json').read_text(encoding='utf-8'))
            self.assertEqual(stats['dimensions']['操作便利性']['mean_difference'],2)
            self.assertFalse(stats['can_claim_real_improvement'])
            chain=json.loads(self.api().artifact(final,'evaluation','v1_v2_chain.json').read_text(encoding='utf-8'))
            self.assertEqual(len(chain['changes']),1)
            self.assertEqual(chain['status'],'simulated_loop_complete')
            cfg=self.config();cfg['generation']['provider']='deepseek'
            with self.assertRaises(ValueError):
                self.api().run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d))


if __name__=='__main__': unittest.main()
