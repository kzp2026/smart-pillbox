"""Research preparation acceptance. HTTP is intercepted; no paid requests or invented real reviews."""
import copy
import io
import json
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment.pipeline.service import run_experiment, resume_experiment, artifact, verify_run
from experiment.pipeline.io import read_json, write_json, sha256
from experiment.pipeline.providers import ResearchTextProvider, configured_provider
from experiment.evaluation.materials import prepare_review_materials
from experiment.audit_methods import audit
from v2.providers.text import DeepSeekTextProvider

ROOT=Path(__file__).resolve().parents[1]


def main():
    root=ROOT/'experiment'/'runs'/('preparation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    source=ROOT/'data/京东智能药盒评论.csv';cfg=read_json(ROOT/'experiment/config.research.json')
    prepared=run_experiment(cfg,source,root/'research_preparation',stop_after='graph')
    materials=prepare_review_materials(prepared,root/'human_materials')
    audit(prepared,root/'method_audit.json')
    missing_c=None
    try:resume_experiment(prepared,cfg,'generation')
    except ValueError as exc:missing_c=str(exc)
    assert missing_c and '审核' in missing_c
    m=verify_run(prepared);assert m['stages']['generation']['status']=='failed' and m['external_api_calls']==0
    # Minimal live-call preflight: A only, one result budget; no paid authorization is supplied.
    minimum=copy.deepcopy(cfg);minimum['generation'].update(groups=['A'],repetitions=1)
    secure=configured_provider(minimum['generation'])
    key_present=bool(secure.backend._api_key)  # Presence only. Never export secrets or hashes of secrets.
    try:run_experiment(minimum,source,root/'live_call_preflight',provider=secure)
    except ValueError as exc:
        preflight=exc.run_path;preflight_reason=str(exc)
    else:raise AssertionError('未授权调用不应成功')
    pm=verify_run(preflight);assert pm['external_api_calls']==0
    # Reviewed paths are synthetic fixtures and only used in transport_test.
    fixtures=root/'SIMULATED_FIXTURES';fixtures.mkdir()
    mappings=read_json(artifact(prepared,'mapping','mappings.json'))
    for row in mappings:
        row.update(review_status='approved',reviewer_id='SIM_REVIEWER',reviewer_note='模拟测试审核，非真实专家',simulated=True)
    review=write_json(fixtures/'SIM_mapping_review.json',mappings)
    test=copy.deepcopy(cfg);test['simulated']=True;test['generation']['mode']='transport_test'
    requests=[]
    class CapturedHTTP:
        def open(self,request,timeout):
            assert request.full_url=='https://api.deepseek.com/chat/completions'
            body=json.loads(request.data.decode('utf-8'));requests.append(body)
            # Do not save Authorization headers. This returned response is explicitly a fixture.
            response={'id':'SIM_RESPONSE_'+str(len(requests)),'model':body['model'],
                'choices':[{'message':{'content':'模拟HTTP响应：设计目标、功能、结构、交互与待验证事项。'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':123,'completion_tokens':20,'total_tokens':143}}
            return io.BytesIO(json.dumps(response,ensure_ascii=False).encode('utf-8'))
    provider=ResearchTextProvider(DeepSeekTextProvider('TEST_ONLY_NOT_A_REAL_KEY',model=test['generation']['model']),allow_paid=True,transport_is_mock=True)
    with patch('urllib.request.build_opener',return_value=CapturedHTTP()):
        simulated=run_experiment(test,source,root/'transport_test',mapping_review=review,provider=provider)
    records=read_json(artifact(simulated,'generation','generation_records.json'))
    assert len(requests)==15 and all(not r['is_real_ai'] and r['simulated'] for r in records)
    for request,record in zip(requests,records):
        assert request==record['actual_request']
        assert json.loads(request['messages'][1]['content'])['used_graph_paths']==record['used_graph_paths']
    cs=[r for r in records if r['group']=='C'];assert all(r['used_graph_paths'] for r in cs)
    write_json(root/'mock_http_requests.json',requests)
    # Persist, reopen and export via the same V2 private service using an isolated SQLite database.
    from v2.adapters.postgres import KnowledgeRepository
    from v2.adapters.storage import LocalArtifactStore
    from v2.application.experiment import ExperimentService
    repo=KnowledgeRepository('sqlite:///'+str(root/'v2_test.sqlite3'),'owner');repo.initialize()
    store=LocalArtifactStore(root/'v2_test_store');service=ExperimentService(repo,store)
    with patch('urllib.request.build_opener',return_value=CapturedHTTP()):
        stored=service.run(test,source,mapping_review=review,provider=provider,request_id='SIM_TRANSPORT_ACCEPTANCE')
        count=len(requests)
        repeated=service.run(test,source,mapping_review=review,provider=provider,request_id='SIM_TRANSPORT_ACCEPTANCE')
        assert len(requests)==count and repeated['pipeline_run_id']==stored['pipeline_run_id']
    loaded=service.load(stored['pipeline_run_id']);assert loaded['manifest']['run_id']==stored['manifest']['run_id']
    archive=service.download(stored['pipeline_run_id']);archive_path=root/'v2_test_export.zip';archive_path.write_bytes(archive)
    restored=root/'v2_test_reopened';restored.mkdir()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(restored)
    verify_run(restored)
    # Detect an already-attempted real job and refuse re-sending, without making any real request.
    fake_cfg=read_json(ROOT/'experiment/config.example.json');fake_cfg['generation']['repetitions']=1
    guard=run_experiment(fake_cfg,source,root/'SIM_resume_guard',stop_after='graph')
    gm=read_json(guard/'run_manifest.json');gm['generation_calls']={'SIM_ATTEMPT':{'request_sent':True}}
    write_json(guard/'run_manifest.json',gm)
    try:resume_experiment(guard,fake_cfg,'generation')
    except ValueError as exc:assert '真实请求' in str(exc)
    else:raise AssertionError('不得自动重发已发送批次')
    inputs_dir=next((prepared/'stages/generation').glob('*/private/inputs'))
    result=dict(status='local_preparation_passed',research_preparation_run=str(prepared),research_manifest=str(prepared/'run_manifest.json'),
        live_preflight_run=str(preflight),live_verification='blocked_not_called',live_preflight_reason=preflight_reason,
        secure_key_present=key_present,paid_authorization_present=False,production_cloud_verified=False,
        real_approved_mapping_count=0,real_expert_rows=0,formal_abc_completed=False,
        transport_test_run=str(simulated),transport_test_manifest=str(simulated/'run_manifest.json'),
        http_transport='mock_intercepted_urllib_request_no_network',http_requests_per_test_run=15,
        c_paths_per_request=len(cs[0]['used_graph_paths']),actual_request_matches_saved_prompt=True,
        input_difference_table=str(inputs_dir/'input_difference_table.md'),human_materials=str(root/'human_materials'),
        counts=m['counts'],method_audit=str(root/'method_audit.json'),
        v2_test_history_reopened=True,v2_test_export=str(archive_path),v2_test_export_sha256=sha256(archive_path),
        duplicate_submit_new_calls=0,charged_resume_blocked=True,materials_missing=materials['missing_items'],
        external_api_calls=0,source_sha256=sha256(source))
    write_json(root/'acceptance.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2));print('ACCEPTANCE_FILE='+str(root/'acceptance.json'))


if __name__=='__main__':main()
