from datetime import UTC, datetime
from typing import cast

import pytest

from app.generation.models import GenerationMessage, GenerationResult
from app.generation.service import GroundedChatService, HistoryTurn, build_retrieval_query
from app.rag.models import ChunkRecord, SourceKind, SourceRecord
from app.rag.retrieval import RetrievalHit, RetrievalService


class StaticRetrieval:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits

    def retrieve(self, query: str) -> list[RetrievalHit]:
        return self.hits


class FakeProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[GenerationMessage]] = []

    async def generate(self, messages: list[GenerationMessage]) -> GenerationResult:
        self.calls.append(messages)
        return GenerationResult(content=self.content)

    async def aclose(self) -> None:
        return None


def make_hit(chunk_id: str, *, score: float, token_count: int) -> RetrievalHit:
    source = SourceRecord(
        source_id=f"source-{chunk_id}",
        kind=SourceKind.FILE,
        title=f"Source {chunk_id}",
        locator=f"{chunk_id}.txt",
        retrieved_at=datetime.now(UTC),
        content_hash=chunk_id,
        content_file=f"{chunk_id}.txt",
        chunk_count=1,
    )
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        source_id=source.source_id,
        source_title=source.title,
        location="Section",
        text=f"Evidence {chunk_id}",
        token_count=token_count,
    )
    return RetrievalHit(chunk=chunk, source=source, score=score)


def test_builds_deterministic_follow_up_query_from_recent_history() -> None:
    history = [
        HistoryTurn(role="user", content="Old topic"),
        HistoryTurn(role="assistant", content="We discussed the AI Maturity Index."),
        HistoryTurn(role="user", content="Does it produce a score?"),
    ]

    query = build_retrieval_query(
        "How do I get started?",
        history,
        recent_history_messages=2,
    )

    assert "Old topic" not in query
    assert query == (
        "Previous assistant: We discussed the AI Maturity Index.\n"
        "Previous user: Does it produce a score?\n"
        "Current question: How do I get started?"
    )


@pytest.mark.anyio
async def test_enforces_score_and_context_budgets_before_generation() -> None:
    accepted_id = "a" * 24
    low_score_id = "b" * 24
    oversized_id = "c" * 24
    retrieval = StaticRetrieval(
        [
            make_hit(accepted_id, score=0.9, token_count=6),
            make_hit(low_score_id, score=0.69, token_count=1),
            make_hit(oversized_id, score=0.8, token_count=5),
        ]
    )
    provider = FakeProvider(f"Supported answer [chunk:{accepted_id}]")
    service = GroundedChatService(
        retrieval_service=cast(RetrievalService, retrieval),
        provider=provider,
        min_score=0.7,
        context_token_budget=10,
    )

    outcome = await service.answer("Question", [])

    assert outcome.abstained is False
    assert outcome.retrieval_count == 1
    context = provider.calls[0][1].content
    assert accepted_id in context
    assert low_score_id not in context
    assert oversized_id not in context
