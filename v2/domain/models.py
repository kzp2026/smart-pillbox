from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DELETING = "deleting"


class ArtifactKind(str, Enum):
    INPUT = "input"
    TABLE = "table"
    DOCUMENT = "document"
    IMAGE = "image"
    ARCHIVE = "archive"
    LEGACY = "legacy"


@dataclass(frozen=True)
class ImportReport:
    product_id: int
    batch_id: int
    input_count: int
    valid_count: int
    invalid_count: int
    inserted_count: int
    duplicate_count: int


@dataclass(frozen=True)
class CreateRunCommand:
    target_product: str
    demand_text: str
    provider: str
    model: str
    image_count: int = 8


@dataclass(frozen=True)
class PipelineRun:
    id: str
    target_product: str
    demand_text: str
    provider: str
    model: str
    image_count: int
    status: RunStatus
    current_stage: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProductSummary:
    id: int
    name: str
    category: str
    description: str
    comment_count: int
    requirement_count: int
    created_at: str
    updated_at: str
