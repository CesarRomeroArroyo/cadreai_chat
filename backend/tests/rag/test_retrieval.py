from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.rag.retrieval import RetrievalService
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore
from tests.rag.fakes import FakeEmbedder


class KeywordEmbedder:
    model_id = "keyword-embedder"
    model_revision = "test-revision"
    dimension = 3

    def __init__(self) -> None:
        self._tokens: dict[str, int] = {}
        self._words: dict[int, str] = {}

    def tokenize(self, text: str) -> list[int]:
        token_ids = []
        for word in text.split():
            token_id = self._tokens.setdefault(word, len(self._tokens) + 1)
            self._words[token_id] = word
            token_ids.append(token_id)
        return token_ids

    def decode(self, token_ids: Sequence[int]) -> str:
        return " ".join(self._words[token_id] for token_id in token_ids)

    def _encode(self, text: str) -> NDArray[np.float32]:
        lowered = text.casefold()
        vector = np.asarray(
            [
                1.0 if "strategy" in lowered else 0.1,
                1.0 if "portal" in lowered else 0.1,
                1.0 if "security" in lowered else 0.1,
            ],
            dtype=np.float32,
        )
        return vector / np.linalg.norm(vector)

    def encode_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        return np.asarray([self._encode(text) for text in texts], dtype=np.float32)

    def encode_query(self, text: str) -> NDArray[np.float32]:
        return self._encode(text)


def make_service(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(
        store=SnapshotStore(tmp_path / "index"),
        embedder=KeywordEmbedder(),
        chunk_tokens=4,
        chunk_overlap=1,
    )


def test_retriever_refreshes_after_atomic_snapshot_change(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    retriever = RetrievalService(service, top_k=2, max_per_source=1)

    assert retriever.readiness().ready is False
    source = service.prepare_file(
        filename="strategy.txt",
        content_type="text/plain",
        data=b"AI strategy planning and leadership guidance",
    )
    service.upsert([source])

    readiness = retriever.readiness()
    hits = retriever.retrieve("strategy services")

    assert readiness.ready is True
    assert readiness.source_count == 1
    assert readiness.chunk_count == 2
    assert len(hits) == 1
    assert hits[0].source.source_id == source.source_id
    assert hits[0].score > 0.9


def test_retrieval_enforces_source_diversity(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    strategy = service.prepare_file(
        filename="strategy.txt",
        content_type="text/plain",
        data=b"strategy planning strategy delivery strategy leadership",
    )
    portal = service.prepare_file(
        filename="portal.txt",
        content_type="text/plain",
        data=b"portal access for strategy clients",
    )
    service.upsert([strategy, portal])
    retriever = RetrievalService(service, top_k=2, max_per_source=1)

    hits = retriever.retrieve("strategy")

    assert len(hits) == 2
    assert {hit.source.source_id for hit in hits} == {strategy.source_id, portal.source_id}
    assert hits[0].score >= hits[1].score


def test_retrieval_uses_lexical_signal_across_full_exact_index(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    distractors = [
        service.prepare_file(
            filename=f"general-{index}.txt",
            content_type="text/plain",
            data=b"AI strategy and security planning guidance",
        )
        for index in range(7)
    ]
    relevant = service.prepare_file(
        filename="construction.txt",
        content_type="text/plain",
        data=b"Construction teams use automated quantity estimating and project monitoring",
    )
    service.upsert([*distractors, relevant])
    retriever = RetrievalService(service, top_k=2, max_per_source=1)

    hits = retriever.retrieve("Do you work with construction companies?")

    assert hits[0].source.source_id == relevant.source_id


def test_retrieval_skips_source_list_sections(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    source = service.prepare_file(
        filename="source-list.md",
        content_type="text/markdown",
        data=(
            b"## Official sources\nhttps://example.com/security\n\n"
            b"## Security\nControlled AI access"
        ),
    )
    service.upsert([source])
    retriever = RetrievalService(service, top_k=2, max_per_source=2)

    hits = retriever.retrieve("security")

    assert hits
    assert all(hit.chunk.location != "Official sources" for hit in hits)


def test_incompatible_snapshot_is_not_ready(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "index")
    original = KnowledgeService(
        store=store,
        embedder=FakeEmbedder(),
        chunk_tokens=8,
        chunk_overlap=2,
    )
    original.rebuild()
    incompatible_embedder = FakeEmbedder()
    incompatible_embedder.model_revision = "other-revision"
    incompatible = KnowledgeService(
        store=store,
        embedder=incompatible_embedder,
        chunk_tokens=8,
        chunk_overlap=2,
    )

    retriever = RetrievalService(incompatible)

    assert retriever.readiness().ready is False
    assert retriever.retrieve("anything") == []
