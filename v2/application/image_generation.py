from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import ArtifactStore
from v2.domain.models import ArtifactKind, RunStatus
from v2.providers.images import ImageGenerationRequest, ImageResult


class ImageProvider(Protocol):
    def generate(self, request: ImageGenerationRequest) -> ImageResult: ...


@dataclass(frozen=True)
class ImageFailure:
    label: str
    error: str


@dataclass(frozen=True)
class ImageGenerationReport:
    requested_count: int
    succeeded_count: int
    artifact_ids: tuple[str, ...]
    failures: tuple[ImageFailure, ...]


class ImageGenerationService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        store: ArtifactStore,
        provider: ImageProvider,
    ) -> None:
        self.repository = repository
        self.store = store
        self.provider = provider

    def generate(
        self,
        run_id: str,
        visual_assets: Sequence[Mapping[str, object]],
        count: int,
        size: str = "1536x1024",
    ) -> ImageGenerationReport:
        selected = list(visual_assets)[: max(0, int(count))]
        if not selected:
            return ImageGenerationReport(0, 0, (), ())

        self.repository.update_pipeline_run(run_id, RunStatus.RUNNING, current_stage="09")
        artifact_ids: list[str] = []
        failures: list[ImageFailure] = []
        for index, asset in enumerate(selected, start=1):
            label = str(asset.get("label") or f"效果图 {index}").strip()
            prompt = str(asset.get("prompt") or "").strip()
            key = self._safe_key(str(asset.get("key") or f"image-{index}"))
            result = self.provider.generate(
                ImageGenerationRequest(
                    prompt=prompt,
                    name=f"{index:02d}-{key}.png",
                    size=size,
                )
            )
            if not result.succeeded:
                failures.append(ImageFailure(label, result.error or "图片生成失败。"))
                continue
            stored = self.store.put(
                run_id,
                f"{index:02d}-{key}.png",
                result.data,
                result.mime_type,
            )
            artifact_ids.append(
                self.repository.record_artifact(run_id, ArtifactKind.IMAGE, stored)
            )

        if failures and artifact_ids:
            status = RunStatus.PARTIAL
        elif failures:
            status = RunStatus.FAILED
        else:
            status = RunStatus.SUCCEEDED
        error_summary = "；".join(f"{item.label}：{item.error}" for item in failures)[:1200]
        self.repository.record_stage_run(run_id, "09", status, error_summary=error_summary)
        self.repository.update_pipeline_run(
            run_id,
            status,
            current_stage="09",
            error_summary=error_summary,
        )
        return ImageGenerationReport(
            len(selected), len(artifact_ids), tuple(artifact_ids), tuple(failures)
        )

    @staticmethod
    def _safe_key(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
        return safe[:48] or "image"
