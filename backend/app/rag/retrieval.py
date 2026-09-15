import re
import threading
from dataclasses import dataclass

import numpy as np

from app.rag.models import ChunkRecord, SourceRecord
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotState

TOKEN_RE = re.compile(r"[a-z0-9]+")
SOURCED_SUMMARY_METADATA_RE = re.compile(
    r"content\s*_\s*type\s*:\s*sourced\s*_\s*summary", re.IGNORECASE
)
STOP_WORDS = {
    "a",
    "ai",
    "an",
    "and",
    "are",
    "cadre",
    "can",
    "company",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "our",
    "the",
    "their",
    "to",
    "we",
    "what",
    "where",
    "with",
    "you",
    "your",
}
TERM_ALIASES = {
    "book": "appointment",
    "booking": "appointment",
    "call": "appointment",
    "connect": "integrate",
    "integration": "integrate",
    "llms": "llm",
    "model": "llm",
    "models": "llm",
    "platform": "system",
    "replace": "integrate",
    "request": "appointment",
    "reservation": "appointment",
    "schedule": "appointment",
    "select": "choose",
    "selection": "choose",
    "software": "system",
    "tool": "system",
    "tools": "system",
}


def _normalize_term(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        term = f"{term[:-3]}y"
    elif term.endswith("ing") and len(term) > 5:
        term = term[:-3]
    elif term.endswith("ed") and len(term) > 4:
        term = term[:-2]
    elif term.endswith("s") and len(term) > 3:
        term = term[:-1]
    return TERM_ALIASES.get(term, term)


def _terms(text: str) -> set[str]:
    return {
        normalized
        for token in TOKEN_RE.findall(text.casefold())
        if token not in STOP_WORDS
        if (normalized := _normalize_term(token)) not in STOP_WORDS
    }


def _lexical_score(query_terms: set[str], searchable_text: str) -> float:
    if not query_terms:
        return 0.0
    document_terms = _terms(searchable_text)
    return len(query_terms & document_terms) / len(query_terms)


def _is_searchable(location: str, text: str) -> bool:
    if location.casefold() == "official sources":
        return False
    stripped = text.strip()
    if stripped.startswith("---") and stripped.endswith("---"):
        return False
    return SOURCED_SUMMARY_METADATA_RE.search(stripped) is None


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
        candidate_count = len(state.chunks)
        scores, positions = state.index.search(query_vector.reshape(1, -1), candidate_count)
        query_terms = _terms(query)
        ranked: list[tuple[float, int]] = []
        for dense_score, position in zip(scores[0], positions[0], strict=True):
            if position < 0:
                continue
            chunk = state.chunks[int(position)]
            if not _is_searchable(chunk.location, chunk.text):
                continue
            source = state.sources[chunk.source_id]
            lexical_score = _lexical_score(
                query_terms,
                f"{source.title} {chunk.location} {chunk.text}",
            )
            combined_score = min(1.0, float(dense_score) + (0.25 * lexical_score))
            ranked.append((combined_score, int(position)))
        ranked.sort(key=lambda item: item[0], reverse=True)

        hits: list[RetrievalHit] = []
        source_counts: dict[str, int] = {}
        for score, position in ranked:
            chunk = state.chunks[position]
            count = source_counts.get(chunk.source_id, 0)
            if count >= self.max_per_source:
                continue
            source = state.sources[chunk.source_id]
            hits.append(RetrievalHit(chunk=chunk, source=source, score=float(score)))
            source_counts[chunk.source_id] = count + 1
            if len(hits) == self.top_k:
                break
        return hits
