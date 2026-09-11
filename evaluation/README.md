# Retrieval evaluation

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
but must be recalibrated against the approved production corpus during Phase 6.
