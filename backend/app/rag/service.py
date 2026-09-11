import hashlib
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.rag.chunking import chunk_source
from app.rag.embedding import Embedder
from app.rag.errors import IndexCompatibilityError, IngestionError
from app.rag.extractors import extract_file, extract_web_content
from app.rag.models import (
    ChunkRecord,
    ExtractedDocument,
    ExtractedSection,
    IngestionResult,
    IngestionStatus,
    PreparedSource,
    SourceKind,
    SourceRecord,
)
from app.rag.store import SnapshotState, SnapshotStore
from app.rag.text import normalize_text
from app.rag.url_fetcher import fetch_url

SAFE_NAME_RE = re.compile(r"[^a-z0-9._-]+")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CHUNKING_VERSION = "token-window-v1"


def _source_id(kind: SourceKind, locator: str) -> str:
    normalized = locator.strip().casefold()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:20]
    return f"{kind.value}-{digest}"


def _content_hash(document: ExtractedDocument) -> str:
    content = "\n\n".join(f"{section.location}\n{section.text}" for section in document.sections)
    return hashlib.sha256(normalize_text(content).encode()).hexdigest()


def _content_filename(source_id: str) -> str:
    safe_name = SAFE_NAME_RE.sub("-", source_id.casefold()).strip("-")
    return f"contents/{safe_name}.json"


def validate_source_id(source_id: str) -> None:
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise IngestionError(
            "Source IDs must use 1-128 letters, numbers, dots, dashes, or underscores"
        )


class KnowledgeService:
    def __init__(
        self,
        *,
        store: SnapshotStore,
        embedder: Embedder,
        chunk_tokens: int = 384,
        chunk_overlap: int = 64,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.chunk_tokens = chunk_tokens
        self.chunk_overlap = chunk_overlap
        self._mutation_lock = threading.Lock()

    def load_state(self) -> SnapshotState:
        state = self.store.load(dimension=self.embedder.dimension)
        metadata = state.metadata
        if metadata is None:
            return state
        expected = (
            self.embedder.model_id,
            self.embedder.model_revision,
            self.chunk_tokens,
            self.chunk_overlap,
            CHUNKING_VERSION,
        )
        actual = (
            metadata.model_id,
            metadata.model_revision,
            metadata.chunk_tokens,
            metadata.chunk_overlap,
            metadata.chunking_version,
        )
        if not metadata.normalized or actual != expected:
            raise IndexCompatibilityError(
                "Active index metadata does not match embedding and chunking configuration"
            )
        return state

    def list_sources(self) -> list[SourceRecord]:
        state = self.load_state()
        return sorted(state.sources.values(), key=lambda source: source.title.casefold())

    def prepare_file(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> PreparedSource:
        document = extract_file(filename, content_type, data)
        return PreparedSource(
            source_id=_source_id(SourceKind.FILE, Path(filename).name),
            kind=SourceKind.FILE,
            title=document.title,
            locator=Path(filename).name,
            retrieved_at=datetime.now(UTC),
            sections=document.sections,
        )

    def prepare_url(
        self,
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: float,
    ) -> PreparedSource:
        canonical_url, content_type, data = fetch_url(
            url,
            allowed_hosts=allowed_hosts,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
        )
        document = extract_web_content(canonical_url, content_type, data)
        return PreparedSource(
            source_id=_source_id(SourceKind.URL, canonical_url),
            kind=SourceKind.URL,
            title=document.title,
            locator=canonical_url,
            retrieved_at=datetime.now(UTC),
            sections=document.sections,
        )

    def upsert(self, prepared_sources: list[PreparedSource]) -> list[IngestionResult]:
        source_ids = [source.source_id for source in prepared_sources]
        if len(source_ids) != len(set(source_ids)):
            raise IngestionError("Ingestion batch contains duplicate source IDs")
        for source_id in source_ids:
            validate_source_id(source_id)
        if not self._mutation_lock.acquire(blocking=False):
            raise IngestionError("Another ingestion operation is already running")
        try:
            return self._upsert_locked(prepared_sources)
        finally:
            self._mutation_lock.release()

    def _upsert_locked(self, prepared_sources: list[PreparedSource]) -> list[IngestionResult]:
        state = self.load_state()
        sources = dict(state.sources)
        contents = dict(state.contents)
        retained = [
            (chunk, vector) for chunk, vector in zip(state.chunks, state.vectors, strict=True)
        ]
        changed_chunks = []
        results: list[IngestionResult] = []
        changed = False

        for prepared in prepared_sources:
            document = ExtractedDocument(title=prepared.title, sections=prepared.sections)
            content_hash = _content_hash(document)
            existing = sources.get(prepared.source_id)
            if existing and existing.content_hash == content_hash:
                results.append(
                    IngestionResult(
                        source_id=prepared.source_id,
                        name=prepared.title,
                        status=IngestionStatus.UNCHANGED,
                        detail="Source content is unchanged",
                        chunk_count=existing.chunk_count,
                    )
                )
                continue
            duplicate = next(
                (
                    source
                    for source in sources.values()
                    if source.content_hash == content_hash
                    and source.source_id != prepared.source_id
                ),
                None,
            )
            if duplicate:
                results.append(
                    IngestionResult(
                        source_id=prepared.source_id,
                        name=prepared.title,
                        status=IngestionStatus.DUPLICATE,
                        detail=f"Content already indexed as {duplicate.title}",
                    )
                )
                continue

            chunks = chunk_source(
                prepared,
                embedder=self.embedder,
                content_hash=content_hash,
                chunk_tokens=self.chunk_tokens,
                chunk_overlap=self.chunk_overlap,
            )
            if not chunks:
                results.append(
                    IngestionResult(
                        source_id=prepared.source_id,
                        name=prepared.title,
                        status=IngestionStatus.ERROR,
                        detail="Source produced no indexable chunks",
                    )
                )
                continue
            retained = [pair for pair in retained if pair[0].source_id != prepared.source_id]
            changed_chunks.extend(chunks)
            contents[prepared.source_id] = prepared.sections
            status = IngestionStatus.UPDATED if existing else IngestionStatus.INDEXED
            sources[prepared.source_id] = SourceRecord(
                source_id=prepared.source_id,
                kind=prepared.kind,
                title=prepared.title,
                locator=prepared.locator,
                retrieved_at=prepared.retrieved_at,
                content_hash=content_hash,
                content_file=_content_filename(prepared.source_id),
                chunk_count=len(chunks),
            )
            results.append(
                IngestionResult(
                    source_id=prepared.source_id,
                    name=prepared.title,
                    status=status,
                    detail="Source indexed successfully",
                    chunk_count=len(chunks),
                )
            )
            changed = True

        if not changed:
            return results
        new_vectors = self.embedder.encode_documents([chunk.text for chunk in changed_chunks])
        all_chunks = [pair[0] for pair in retained] + changed_chunks
        retained_vectors = (
            np.asarray([pair[1] for pair in retained], dtype=np.float32)
            if retained
            else np.empty((0, self.embedder.dimension), dtype=np.float32)
        )
        vectors = np.concatenate((retained_vectors, new_vectors), axis=0)
        self._activate(sources, contents, all_chunks, vectors)
        return results

    def remove(self, source_id: str) -> bool:
        if not self._mutation_lock.acquire(blocking=False):
            raise IngestionError("Another ingestion operation is already running")
        try:
            state = self.load_state()
            if source_id not in state.sources:
                return False
            sources = dict(state.sources)
            contents = dict(state.contents)
            del sources[source_id]
            del contents[source_id]
            retained = [
                (chunk, vector)
                for chunk, vector in zip(state.chunks, state.vectors, strict=True)
                if chunk.source_id != source_id
            ]
            chunks = [pair[0] for pair in retained]
            vectors = (
                np.asarray([pair[1] for pair in retained], dtype=np.float32)
                if retained
                else np.empty((0, self.embedder.dimension), dtype=np.float32)
            )
            self._activate(sources, contents, chunks, vectors)
            return True
        finally:
            self._mutation_lock.release()

    def rebuild(self) -> int:
        if not self._mutation_lock.acquire(blocking=False):
            raise IngestionError("Another ingestion operation is already running")
        try:
            sources, contents, _ = self.store.load_source_data()
            all_chunks = []
            updated_sources: dict[str, SourceRecord] = {}
            for source_id, source in sources.items():
                prepared = PreparedSource(
                    source_id=source_id,
                    kind=source.kind,
                    title=source.title,
                    locator=source.locator,
                    retrieved_at=datetime.now(UTC),
                    sections=contents[source_id],
                )
                chunks = chunk_source(
                    prepared,
                    embedder=self.embedder,
                    content_hash=source.content_hash,
                    chunk_tokens=self.chunk_tokens,
                    chunk_overlap=self.chunk_overlap,
                )
                updated_sources[source_id] = source.model_copy(update={"chunk_count": len(chunks)})
                all_chunks.extend(chunks)
            vectors = self.embedder.encode_documents([chunk.text for chunk in all_chunks])
            self._activate(updated_sources, contents, all_chunks, vectors)
            return len(all_chunks)
        finally:
            self._mutation_lock.release()

    def _activate(
        self,
        sources: dict[str, SourceRecord],
        contents: dict[str, tuple[ExtractedSection, ...]],
        chunks: list[ChunkRecord],
        vectors: NDArray[np.float32],
    ) -> None:
        self.store.activate(
            sources=sources,
            contents=contents,
            chunks=chunks,
            vectors=vectors,
            model_id=self.embedder.model_id,
            model_revision=self.embedder.model_revision,
            dimension=self.embedder.dimension,
            chunk_tokens=self.chunk_tokens,
            chunk_overlap=self.chunk_overlap,
            chunking_version=CHUNKING_VERSION,
        )
