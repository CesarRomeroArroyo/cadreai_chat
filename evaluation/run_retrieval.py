import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml
from app.generation.service import HistoryTurn, build_retrieval_query
from app.rag.embedding import SentenceTransformerEmbedder
from app.rag.models import ExtractedSection, PreparedSource, SourceKind
from app.rag.retrieval import RetrievalService
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "retrieval_cases.yaml"
MODEL_ID = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate local retrieval without generation"
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "backend" / ".cache" / "models"
    )
    parser.add_argument("--min-score", type=float, default=0.7)
    return parser.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported retrieval evaluation dataset")
    return cast(dict[str, Any], payload)


def main() -> int:
    args = parse_args()
    dataset = load_dataset(args.dataset)
    embedder = SentenceTransformerEmbedder(
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        cache_dir=args.cache_dir,
        local_files_only=True,
        cpu_threads=1,
    )
    with tempfile.TemporaryDirectory(prefix="cadre-retrieval-eval-") as temporary:
        knowledge = KnowledgeService(
            store=SnapshotStore(Path(temporary) / "index"),
            embedder=embedder,
            chunk_tokens=384,
            chunk_overlap=64,
        )
        sources = [
            PreparedSource(
                source_id=str(item["source_id"]),
                kind=SourceKind.FILE,
                title=str(item["title"]),
                locator=f"{item['source_id']}.txt",
                retrieved_at=datetime.now(UTC),
                sections=(
                    ExtractedSection(
                        location="Evaluation fixture", text=str(item["text"])
                    ),
                ),
            )
            for item in dataset["sources"]
        ]
        knowledge.upsert(sources)
        retrieval = RetrievalService(knowledge, top_k=6, max_per_source=2)
        failures = 0
        results = []
        for item in dataset["cases"]:
            history = [
                HistoryTurn(role=turn["role"], content=turn["content"])
                for turn in item["history"]
            ]
            query = build_retrieval_query(str(item["question"]), history)
            hits = retrieval.retrieve(query)
            accepted = [hit for hit in hits if hit.score >= args.min_score]
            source_ids = list(dict.fromkeys(hit.source.source_id for hit in accepted))
            expected = set(item["expected_source_ids"])
            passed = (
                not accepted if item["must_abstain"] else expected.issubset(source_ids)
            )
            failures += not passed
            results.append(
                {
                    "case_id": item["case_id"],
                    "passed": passed,
                    "source_ids": source_ids,
                    "top_score": round(hits[0].score, 4) if hits else None,
                }
            )
        print(
            json.dumps(
                {
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "min_score": args.min_score,
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
