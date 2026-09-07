import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiment.pipeline.graph import apply_reviews,build_graph
from experiment.pipeline.semantics import derive_requirements,candidate_mappings
from experiment.pipeline.service import run_experiment,artifact,verify_run

ROOT=Path(__file__).resolve().parents[1]


class IntegrityTests(unittest.TestCase):
    def fixture(self):
        rows=[dict(comment_id='C0001',cleaned_comment='提醒声音太小，听不清')]
        req=derive_requirements(rows);return rows,req,candidate_mappings(req)

    def test_generic_praise_is_not_formal_requirement(self):
        result=derive_requirements([dict(comment_id='C0001',text='很好用，非常好，不错')])
        self.assertTrue(all(r['review_status']=='needs_naming' for r in result))
        self.assertEqual(candidate_mappings(result),[])

    def test_reviews_cannot_change_source_evidence(self):
        comments,req,rows=self.fixture();edit=copy.deepcopy(rows[0]);edit['source_comment_ids']=['C9999']
        with self.assertRaises(ValueError):apply_reviews(rows,[edit],req)

    def test_simulated_approval_is_rejected_in_formal_graph(self):
        comments,req,rows=self.fixture();edit=copy.deepcopy(rows[0]);edit.update(review_status='approved',reviewer_id='SIM_R01',reviewer_note='模拟')
        with self.assertRaises(ValueError):apply_reviews(rows,[edit],req)
        approved=apply_reviews(rows,[edit],req,simulated=True)
        with self.assertRaises(ValueError):build_graph(approved,comments)

    def test_graph_validates_approved_metadata_not_just_status(self):
        comments,req,rows=self.fixture();rows[0]['review_status']='approved'
        with self.assertRaises(ValueError):build_graph(rows,comments)

    def test_reproducible_source_snapshot_is_saved(self):
        cfg=json.loads((ROOT/'experiment/config.example.json').read_text(encoding='utf-8'));cfg['generation']['repetitions']=1
        with tempfile.TemporaryDirectory() as d:
            run=run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d),stop_after='clean')
            self.assertTrue((run/'source/experiment/pipeline/service.py').exists())
            self.assertEqual(verify_run(run)['source_files']['pipeline/service.py'],__import__('hashlib').sha256((run/'source/experiment/pipeline/service.py').read_bytes()).hexdigest())

    def test_unknown_config_types_rejected(self):
        cfg=json.loads((ROOT/'experiment/config.example.json').read_text(encoding='utf-8'));cfg['cleaning']['deduplicate']='false'
        from experiment.pipeline.service import validate_config
        with self.assertRaises(ValueError):validate_config(cfg)

    def test_upstream_resume_invalidates_downstream_artifacts(self):
        from experiment.pipeline.service import resume_experiment,read_manifest
        cfg=json.loads((ROOT/'experiment/config.example.json').read_text(encoding='utf-8'));cfg['generation']['repetitions']=1
        with tempfile.TemporaryDirectory() as d:
            run=run_experiment(cfg,ROOT/'data/京东智能药盒评论.csv',Path(d))
            resume_experiment(run,cfg,'topics',stop_after='topics')
            self.assertNotEqual(read_manifest(run)['stages']['generation']['status'],'completed')
            with self.assertRaises(ValueError):artifact(run,'generation','generation_records.json')


if __name__=='__main__':unittest.main()
