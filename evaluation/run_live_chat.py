import argparse
import json
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "live_chat_cases.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run opt-in live chat evaluation")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default="http://127.0.0.1:8012")
    parser.add_argument("--max-cases", type=int, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--confirm-paid-api", action="store_true")
    return parser.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported live chat evaluation dataset")
    return cast(dict[str, Any], payload)


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Live evaluation must target a local HTTP backend")
    if parsed.port is None:
        raise ValueError("Live evaluation URL must include a port")
    return base_url.rstrip("/")


def main() -> int:
    args = parse_args()
    if not args.confirm_paid_api:
        raise SystemExit("Refusing paid evaluation without --confirm-paid-api")
    if args.max_cases < 1 or args.max_cases > 20:
        raise SystemExit("--max-cases must be between 1 and 20")

    dataset = load_dataset(args.dataset)
    selected_ids = set(args.case_id)
    cases = [
        item
        for item in dataset["cases"]
        if not selected_ids or item["case_id"] in selected_ids
    ][: args.max_cases]
    missing_ids = selected_ids - {str(item["case_id"]) for item in cases}
    if missing_ids:
        raise SystemExit(
            f"Unknown or excluded case IDs: {', '.join(sorted(missing_ids))}"
        )
    base_url = validate_base_url(args.base_url)
    results: list[dict[str, object]] = []
    previous_history: list[dict[str, str]] = []

    with httpx.Client(timeout=120) as client:
        for item in cases:
            question = str(item["question"])
            history = previous_history if item.get("use_previous") else []
            started = time.perf_counter()
            response = client.post(
                f"{base_url}/api/v1/chat",
                json={"message": question, "history": history},
            )
            latency_ms = round((time.perf_counter() - started) * 1000)
            payload = response.json()
            result = {
                "case_id": str(item["case_id"]),
                "expectation": str(item["expectation"]),
                "status": response.status_code,
                "latency_ms": latency_ms,
                "answer": payload.get("answer") if isinstance(payload, dict) else None,
                "abstained": payload.get("abstained")
                if isinstance(payload, dict)
                else None,
                "sources": payload.get("sources")
                if isinstance(payload, dict)
                else None,
                "request_id": (
                    payload.get("request_id")
                    if isinstance(payload, dict)
                    else response.headers.get("x-request-id")
                ),
                "error": payload.get("error") if isinstance(payload, dict) else None,
            }
            results.append(result)
            if response.status_code == 200 and isinstance(result["answer"], str):
                previous_history = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": result["answer"]},
                ]
            else:
                previous_history = []

    print(
        json.dumps(
            {
                "model_calls_authorized": len(cases),
                "total": len(results),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if all(result["status"] == 200 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
