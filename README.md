# Cadre AI Support Chatbot

Grounded customer support chatbot for Cadre AI. The application uses a React/Vite client, a FastAPI service, local embeddings, and a persisted FAISS index.

## Current status

Phase 6 is complete. Retrieval and generated-answer evaluations, integrated chat coverage, dependency
hardening, grounded orchestration, and the responsive public UI are implemented, tested, and deployed.
Approved production sources and production generation credentials remain pending, so the public chat
currently abstains.

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

The backend exposes `GET /health`, `GET /ready`, protected knowledge APIs, and `POST /api/v1/chat`.
Provider mode defaults to `disabled`; chat abstains without evidence and fails closed if evidence exists
while generation is unavailable.

## Architecture and trust boundaries

The public chat follows one bounded path:

```text
React client
  -> FastAPI validation and per-IP rate limit
  -> local query embedding and FAISS retrieval
  -> score, diversity, and context-budget filters
  -> configured OpenAI-compatible provider
  -> citation allowlist and URL removal
  -> trusted source metadata from the backend
```

Conversation history helps interpret follow-ups but is untrusted and never treated as evidence. Retrieved
text is escaped and delimited as untrusted reference data. Only backend-issued chunk IDs supplied in the
current context can become citations, and user-visible source URLs come from stored source metadata rather
than model output.

Provider configuration is backend-only. Input characters, history messages, total history characters,
retrieval candidates, context tokens, output tokens, timeout, temperature, retries, request bytes, and
request rate all have configured limits. There is no automatic provider fallback.

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
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_generation.py
```

Frontend and backend tests are local and do not call paid APIs. Retrieval evaluation uses only the
cached pinned embedding model and synthetic fixtures that are never added to production knowledge.
Generated-answer evaluation uses a deterministic fake provider and tests orchestration separately from
retrieval quality.

## Deployment

The current application runs on the existing DigitalOcean Droplet without Docker:

- Nginx serves the static frontend and proxies backend routes.
- One systemd-managed Uvicorn worker listens only on `127.0.0.1:8010`.
- Releases are immutable under `/opt/cadre-ai/releases`.
- `current` and `previous` symlinks support atomic rollback.
- Persistent model/index directories live under `/var/lib/cadre-ai`.
- Production environment values live outside Git under `/etc/cadre-ai`.

See `deploy/digitalocean/README.md` for deployment, rollback, and first-deployment removal procedures.

## Security

Never commit provider keys. Backend environment examples contain fictitious values only; browser code must never receive OpenAI or OpenRouter credentials.

Production loads one immutable, pinned embedding model revision from local files. Approved knowledge files
cannot replace model files. Dependency audits currently report no known vulnerabilities in production
Python or frontend packages.

## Current limitations

- Production knowledge is empty and provider mode is `disabled`; public questions therefore abstain.
- The provisional `0.7` retrieval score floor passed synthetic evaluation but requires recalibration with
  approved production content. Similarity scores are ranking signals, not truth probabilities.
- Prompt delimiting and citation validation reduce but cannot eliminate model hallucination or injection.
- In-memory rate limits reset on restart and do not coordinate across workers or hosts.
- The MVP has no persisted chats, end-user authentication, OCR, actions, or distributed abuse controls.
- Production uses one backend worker and local filesystem state.

See `plan.md` for phased scope, architecture, risks, and acceptance criteria.
