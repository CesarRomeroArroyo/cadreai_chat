# Cadre AI Support Chatbot

Grounded customer support chatbot for Cadre AI. The planned application uses a React/Vite client, a FastAPI service, local embeddings, and a persisted FAISS index.

## Current status

Phase 1 establishes the repository, development tooling, backend health endpoint, and frontend shell. Chat, ingestion, retrieval, and generation are intentionally not implemented yet.

## Repository layout

```text
frontend/  React, Vite, and strict TypeScript
backend/   FastAPI application and tests
docs/      Challenge specification and project notes
```

## Prerequisites

- Node.js 22+
- pnpm 11+
- Python 3.12

## Development

Install dependencies from the repository root:

```bash
pnpm install
uv sync --project backend --extra dev
```

Run each application in a separate terminal:

```bash
pnpm --dir frontend dev
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload
```

The backend currently exposes `GET /health`. Chat and readiness endpoints are scheduled for later phases.

## Verification

```bash
pnpm --dir frontend lint
pnpm --dir frontend test
pnpm --dir frontend build

backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
backend/.venv/bin/mypy backend/app backend/tests
backend/.venv/bin/pytest backend/tests
```

Frontend and backend tests are local and do not call paid APIs.

## Security

Never commit provider keys. Backend environment examples contain fictitious values only; browser code must never receive OpenAI or OpenRouter credentials.

See `plan.md` for phased scope, architecture, risks, and acceptance criteria.
