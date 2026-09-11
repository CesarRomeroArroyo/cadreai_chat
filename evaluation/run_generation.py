import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml
from app.generation.models import GenerationMessage, GenerationResult, TokenUsage
from app.generation.service import GroundedChatService, HistoryTurn
from app.rag.models import ChunkRecord, SourceKind, SourceRecord
from app.rag.retrieval import RetrievalHit, RetrievalService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "generation_cases.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate grounded-answer controls with a deterministic fake provider"
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    return parser.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported generation evaluation dataset")
    return cast(dict[str, Any], payload)


def chunk_id(source_id: str) -> str:
    return hashlib.sha256(source_id.encode()).hexdigest()[:24]


def build_hits(dataset: dict[str, Any]) -> dict[str, RetrievalHit]:
    hits: dict[str, RetrievalHit] = {}
    for item in dataset["sources"]:
        source_id = str(item["source_id"])
        kind = SourceKind(str(item["kind"]))
        source = SourceRecord(
            source_id=source_id,
            kind=kind,
            title=str(item["title"]),
            locator=str(item["locator"]),
            retrieved_at=datetime.now(UTC),
            content_hash=hashlib.sha256(str(item["text"]).encode()).hexdigest(),
            content_file=f"{source_id}.txt",
            chunk_count=1,
        )
        chunk = ChunkRecord(
            chunk_id=chunk_id(source_id),
            source_id=source_id,
            source_title=source.title,
            location=str(item["location"]),
            text=str(item["text"]),
            token_count=max(1, len(str(item["text"]).split())),
        )
        hits[source_id] = RetrievalHit(chunk=chunk, source=source, score=0.95)
    return hits


class StaticRetrieval:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.queries: list[str] = []

    def retrieve(self, query: str) -> list[RetrievalHit]:
        self.queries.append(query)
        return self.hits


class FakeProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[GenerationMessage]] = []

    async def generate(self, messages: list[GenerationMessage]) -> GenerationResult:
        self.calls.append(messages)
        return GenerationResult(
            content=self.content,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=25, total_tokens=125),
        )

    async def aclose(self) -> None:
        return None


def resolve_citations(answer: str, hits: dict[str, RetrievalHit]) -> str:
    resolved = answer
    for source_id, hit in hits.items():
        resolved = resolved.replace(f"{{{{chunk:{source_id}}}}}", hit.chunk.chunk_id)
    return resolved


async def evaluate_case(
    item: dict[str, Any], all_hits: dict[str, RetrievalHit]
) -> dict[str, object]:
    selected = [all_hits[str(source_id)] for source_id in item["retrieved_source_ids"]]
    retrieval = StaticRetrieval(selected)
    provider = FakeProvider(resolve_citations(str(item["provider_answer"]), all_hits))
    service = GroundedChatService(
        retrieval_service=cast(RetrievalService, retrieval),
        provider=provider,
        min_score=0.7,
        context_token_budget=1800,
        recent_history_messages=4,
    )
    history = [
        HistoryTurn(role=turn["role"], content=str(turn["content"]))
        for turn in item["history"]
    ]
    outcome = await service.answer(str(item["question"]), history)
    source_ids = [source.source_id for source in outcome.sources]
    prompt = "\n".join(message.content for call in provider.calls for message in call)
    checks = {
        "abstention": outcome.abstained is bool(item["expected_abstained"]),
        "sources": source_ids == [str(value) for value in item["expected_source_ids"]],
        "answer_contains": all(
            str(value) in outcome.answer for value in item["expected_answer_contains"]
        ),
        "answer_excludes": all(
            str(value) not in outcome.answer
            for value in item["forbidden_answer_contains"]
        ),
        "provider_calls": len(provider.calls) == int(item["expected_provider_calls"]),
        "prompt_contains": all(
            str(value) in prompt for value in item.get("expected_prompt_contains", [])
        ),
        "prompt_excludes": all(
            str(value) not in prompt
            for value in item.get("forbidden_prompt_contains", [])
        ),
        "query_contains": all(
            str(value) in retrieval.queries[0]
            for value in item.get("expected_query_contains", [])
        ),
    }
    return {
        "case_id": str(item["case_id"]),
        "passed": all(checks.values()),
        "checks": checks,
        "abstained": outcome.abstained,
        "source_ids": source_ids,
        "provider_calls": len(provider.calls),
    }


async def run(dataset: dict[str, Any]) -> list[dict[str, object]]:
    hits = build_hits(dataset)
    return [await evaluate_case(item, hits) for item in dataset["cases"]]


def main() -> int:
    dataset = load_dataset(parse_args().dataset)
    results = asyncio.run(run(dataset))
    failures = sum(not bool(result["passed"]) for result in results)
    print(
        json.dumps(
            {
                "provider": "deterministic-fake",
                "passed": len(results) - failures,
                "total": len(results),
                "cases": results,
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
