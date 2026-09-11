from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SourceKind(StrEnum):
    FILE = "file"
    URL = "url"


class IngestionStatus(StrEnum):
    INDEXED = "indexed"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"
    ERROR = "error"


class SourceRecord(BaseModel):
    source_id: str
    kind: SourceKind
    title: str
    locator: str
    retrieved_at: datetime
    content_hash: str
    content_file: str
    chunk_count: int


class ChunkRecord(BaseModel):
    chunk_id: str
    source_id: str
    source_title: str
    location: str
    text: str
    token_count: int


class IndexMetadata(BaseModel):
    snapshot_id: str
    created_at: datetime
    model_id: str
    model_revision: str
    dimension: int
    normalized: bool = True
    chunking_version: str
    chunk_tokens: int
    chunk_overlap: int
    source_count: int
    chunk_count: int


class IngestionResult(BaseModel):
    source_id: str | None
    name: str
    status: IngestionStatus
    detail: str
    chunk_count: int = 0


@dataclass(frozen=True)
class ExtractedSection:
    location: str
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    title: str
    sections: tuple[ExtractedSection, ...]


@dataclass(frozen=True)
class PreparedSource:
    source_id: str
    kind: SourceKind
    title: str
    locator: str
    retrieved_at: datetime
    sections: tuple[ExtractedSection, ...]
