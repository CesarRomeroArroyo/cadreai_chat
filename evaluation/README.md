# Evaluation

## Retrieval

`retrieval_cases.yaml` contains synthetic, test-only sources and representative direct,
follow-up, abstention, and prompt-injection cases. These fixtures are not approved production
knowledge and must never be copied into `backend/data/documents` or the production index.

Run the evaluation from the repository root with the pinned model already cached:

```bash
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_retrieval.py
```

The runner uses `local_files_only=True`, creates a temporary index, performs no generation call,
prints per-case source IDs and top scores, and exits non-zero when expectations fail. The score
floor is a retrieval filter, not a probability or factual-confidence claim.

Current provisional floor is `0.7`. It separates all seven synthetic cases with the pinned model,
but must be recalibrated against approved production content after that content is available.

## Generated answers

`generation_cases.yaml` evaluates answer controls separately from retrieval quality. It covers valid
citations, follow-up context, uncited and fabricated answers, URL removal, no-evidence abstention,
trusted source mapping, and escaped prompt-injection content.

```bash
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_generation.py
```

The runner uses a deterministic fake provider and static synthetic retrieval hits. It makes no model,
network, or paid API call. This verifies orchestration and deterministic output controls; it does not
measure factual quality of a production conversational model.

## Opt-in live chat

`live_chat_cases.yaml` contains the manually reviewed product scenarios. The runner targets only a local
backend and refuses to run without both an explicit case limit and paid-API confirmation:

```bash
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_live_chat.py \
  --max-cases 20 \
  --confirm-paid-api
```

This command can call the configured generation provider and consume paid tokens. Review its answers,
citations, abstentions, and source metadata manually; HTTP success alone is not answer-quality success.
Use repeatable `--case-id CASE_ID` options to rerun only selected cases.
