from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path

from v2.application.history import HistoryService
from v2.domain.models import ArtifactKind, CreateRunCommand, RunStatus
from v2.research.analysis import analyze
from v2.research.dataset import VERSION, canonical_bytes, digest
from v2.research.evaluation import evaluate_predictions, readiness, summarize_reviews
from v2.research.report import build_archive
from v2.research.provenance import source_snapshot


def environment_manifest() -> dict:
    dependencies = {}
    for name in ('pandas','numpy','scikit-learn','scipy','snownlp','matplotlib','python-docx','streamlit'):
        try: dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: dependencies[name] = 'not-installed'
    hashes = {p:hashlib.sha256(data).hexdigest() for p,data in source_snapshot().items()}
    return dict(version=VERSION, python=platform.python_version(), dependencies=dependencies,
                source_files=hashes, source_sha256=digest(hashes),
                model='offline-statistical-and-rule-baselines', prompt_version='not-used',
                external_api_calls=0)


class ResearchService:
    """Private immutable experiment snapshots reuse the existing run/artifact schema."""
    def __init__(self, repository, store):
        self.repository, self.store = repository, store

    def run(self, product: str, dataset: dict, config: dict, gold: list[dict] | None = None,
            reviews: list[dict] | None = None, schemes: list[dict] | None = None,
            human_confirmed: bool = False, nonce: str | None = None, parent_id: str = '',
            external_predictions: list[dict] | None = None, method_notes: str = '') -> dict:
        product = product.strip()
        if not product: raise ValueError('请输入产品名称。')
        gold, reviews, schemes = gold or [], reviews or [], schemes or []
        external_predictions = external_predictions or []
        if external_predictions and not method_notes.strip():
            raise ValueError('导入候选方法预测时必须填写模型/版本、参数、提示词版本与训练数据使用说明。')
        if (gold or reviews) and not human_confirmed:
            raise ValueError('提交人工标注或评分前，须确认其真实来源及独立评价用途。')
        if dataset['card']['dataset_sha256'] != digest(dataset['records']):
            raise ValueError('数据集摘要不匹配，请重新准备数据。')
        self.repository.upsert_product(product)
        started = datetime.now(timezone.utc).isoformat()
        manifest = environment_manifest()
        # Run identity includes inputs/config rather than trusting a client nonce alone.
        identity = digest([product,dataset,config,gold,reviews,schemes,human_confirmed,parent_id,external_predictions,method_notes,manifest,nonce or str(uuid.uuid4())])
        run = self.repository.create_pipeline_run(CreateRunCommand(product,'论文实验：数据与证据验证','research',VERSION,0), 'research:'+identity)
        existing = self.repository.get_generation_run(run.id)
        if existing and run.status == RunStatus.SUCCEEDED: return self.load(run.id)
        self.repository.update_pipeline_run(run.id, RunStatus.RUNNING, current_stage='research')
        try:
            analysis = analyze(dataset['records'], **config)
            analysis['predictions'].extend(external_predictions)
            analysis['methods']['external'] = {'methods': sorted({str(r.get('method','')) for r in external_predictions}),
                                                'notes': method_notes, 'reproduction': 'imported predictions, not rerunning external models'}
            evaluation = evaluate_predictions(gold, analysis['predictions'], {r['comment_id'] for r in dataset['records']})
            summary = summarize_reviews(reviews, {s['scheme_id'] for s in schemes})
            manifest.update(run_id=run.id, parent_id=parent_id, started_at=started,
                            finished_at=datetime.now(timezone.utc).isoformat(), config=config,
                            input_sha256=dataset['card']['input_sha256'], dataset_sha256=dataset['card']['dataset_sha256'],
                            human_source_confirmed=human_confirmed)
            experiment = dict(product=product, manifest=manifest, dataset=dataset, analysis=analysis,
                              evaluation=evaluation, gold=gold, reviews=reviews, review_summary=summary, schemes=schemes,
                              external_predictions=external_predictions, method_notes=method_notes)
            experiment['readiness'] = readiness(dataset,analysis,evaluation,summary,human_confirmed)
            archive = build_archive(experiment)
            stored = self.store.put(run.id,'paper-evidence.zip',archive,'application/zip')
            self.repository.record_artifact(run.id,ArtifactKind.ARCHIVE,stored)
            self.repository.save_generation_run(run.id, '{}', canonical_bytes({'research':experiment}).decode('utf-8'),0,'research_not_design_score')
            self.repository.update_pipeline_run(run.id,RunStatus.SUCCEEDED,current_stage='research')
            return experiment
        except Exception:
            self.repository.update_pipeline_run(run.id,RunStatus.FAILED,current_stage='research')
            raise

    def load(self, run_id: str) -> dict:
        detail = HistoryService(self.repository,self.store).reopen(run_id)
        if 'research' not in detail.result: raise ValueError('此记录不是完整论文实验。')
        return detail.result['research']

    def download(self, run_id: str) -> bytes:
        rows = self.repository.list_artifacts_for_run(run_id)
        artifact = next((r for r in rows if r['name']=='paper-evidence.zip'),None)
        if not artifact: raise ValueError('实验归档尚未生成。')
        data = self.store.read(artifact['storage_path'])
        if hashlib.sha256(data).hexdigest() != artifact['sha256']: raise ValueError('归档校验失败，请勿作为论文证据使用。')
        return data

    def replay(self, run_id: str) -> dict:
        old=self.load(run_id)
        return self.run(old['product'],old['dataset'],old['manifest']['config'],old['gold'],old['reviews'],old['schemes'],
                        old['manifest']['human_source_confirmed'],parent_id=run_id,
                        external_predictions=old.get('external_predictions',[]),method_notes=old.get('method_notes',''))
