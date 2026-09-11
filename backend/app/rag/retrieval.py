import threading
from dataclasses import dataclass

import numpy as np

from app.rag.models import ChunkRecord, SourceRecord
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotState


@dataclass(frozen=True)
class RetrievalHit:
    chunk: ChunkRecord
    source: SourceRecord
    score: float


@dataclass(frozen=True)
class ReadinessState:
    ready: bool
    source_count: int = 0
    chunk_count: int = 0


class RetrievalService:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        *,
        top_k: int = 6,
        max_per_source: int = 2,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.top_k = top_k
        self.max_per_source = max_per_source
        self._lock = threading.Lock()
        self._snapshot_id: str | None = None
        self._state: SnapshotState | None = None
        self._load_error: Exception | None = None
        self.refresh(force=True)

    def refresh(self, *, force: bool = False) -> None:
        current_id = self.knowledge_service.store.active_snapshot_id()
        if not force and current_id == self._snapshot_id:
            return
        with self._lock:
            current_id = self.knowledge_service.store.active_snapshot_id()
            if not force and current_id == self._snapshot_id:
                return
            try:
                state = self.knowledge_service.load_state()
            except (OSError, RuntimeError, ValueError) as exc:
                self._state = None
                self._load_error = exc
            else:
                self._state = state
                self._load_error = None
            self._snapshot_id = current_id

    def readiness(self) -> ReadinessState:
        self.refresh()
        state = self._state
        if state is None or state.metadata is None or self._load_error is not None:
            return ReadinessState(ready=False)
        return ReadinessState(
            ready=True,
            source_count=len(state.sources),
            chunk_count=len(state.chunks),
        )

    def retrieve(self, query: str) -> list[RetrievalHit]:
        self.refresh()
        state = self._state
        if state is None or state.metadata is None or not state.chunks:
            return []
        query_vector = np.asarray(
            self.knowledge_service.embedder.encode_query(query), dtype=np.float32
        )
        expected_shape = (self.knowledge_service.embedder.dimension,)
        if query_vector.shape != expected_shape or not np.isfinite(query_vector).all():
            raise RuntimeError("Query embedding is invalid")
        candidate_count = min(len(state.chunks), self.top_k * max(self.max_per_source, 2))
        scores, positions = state.index.search(query_vector.reshape(1, -1), candidate_count)
        hits: list[RetrievalHit] = []
        source_counts: dict[str, int] = {}
        for score, position in zip(scores[0], positions[0], strict=True):
            if position < 0:
                continue
            chunk = state.chunks[int(position)]
            count = source_counts.get(chunk.source_id, 0)
            if count >= self.max_per_source:
                continue
            source = state.sources[chunk.source_id]
            hits.append(RetrievalHit(chunk=chunk, source=source, score=float(score)))
            source_counts[chunk.source_id] = count + 1
            if len(hits) == self.top_k:
                break
        return hits
