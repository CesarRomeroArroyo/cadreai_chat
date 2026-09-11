# Cadre AI Support Chatbot

Grounded customer support chatbot for Cadre AI. The application uses a React/Vite client, a FastAPI service, local embeddings, and a persisted FAISS index.

## Current status

Phase 4 is in progress. Local retrieval, readiness, grounded chat orchestration, and the
OpenAI-compatible provider adapter are implemented and tested. Production deployment of this backend
checkpoint and the interactive chat UI remain pending.

Public deployment: <https://cadre-ai.164.90.135.146.nip.io>

Protected knowledge console: <https://cadre-ai.164.90.135.146.nip.io/knowledge>

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
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_retrieval.py
```

Frontend and backend tests are local and do not call paid APIs. Retrieval evaluation uses only the
cached pinned embedding model and synthetic fixtures that are never added to production knowledge.

## Deployment

The current application foundation runs on the existing DigitalOcean Droplet without Docker:

- Nginx serves the static frontend and proxies backend routes.
- One systemd-managed Uvicorn worker listens only on `127.0.0.1:8010`.
- Releases are immutable under `/opt/cadre-ai/releases`.
- `current` and `previous` symlinks support atomic rollback.
- Persistent model/index directories live under `/var/lib/cadre-ai`.
- Production environment values live outside Git under `/etc/cadre-ai`.

See `deploy/digitalocean/README.md` for deployment, rollback, and first-deployment removal procedures.

## Security

Never commit provider keys. Backend environment examples contain fictitious values only; browser code must never receive OpenAI or OpenRouter credentials.

See `plan.md` for phased scope, architecture, risks, and acceptance criteria.
