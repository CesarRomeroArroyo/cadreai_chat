# Cadre AI Support Chatbot

Grounded customer support chatbot for Cadre AI. The application uses a React/Vite client, a FastAPI service, local embeddings, and a persisted FAISS index.

## Current status

Implementation and local validation are complete. The versioned knowledge set contains 12 reviewed
summaries and two official URL sources. A real-provider local evaluation with `gpt-5.6-luna` passed all
20 product and safety scenarios. OpenRouter configuration is included but remains disabled by default.

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
- uv 0.10+

## Development

Create backend configuration from the repository root:

```bash
cp backend/.env.example backend/.env
```

Replace these fictitious values in `backend/.env`:

```text
KNOWLEDGE_ADMIN_PASSWORD=<random password of at least 16 characters>
KNOWLEDGE_SESSION_SECRET=<independent random signing secret>
CHAT_API_KEY=<your OpenRouter API key>
CHAT_PROVIDER=openrouter
```

`backend/.env` is ignored by Git. Never place provider credentials in `VITE_*`, frontend files,
committed configuration, screenshots, logs, or submission archives.

OpenRouter configuration supplied by the example:

```text
CHAT_BASE_URL=https://openrouter.ai/api/v1
CHAT_MODEL=openai/gpt-5.6-luna
CHAT_MAX_OUTPUT_TOKENS=400
CHAT_PROVIDER_RETRIES=1
```

Current OpenRouter catalog pricing observed on 2026-09-15 was USD 0.20 per million input tokens and
USD 1.20 per million output tokens. Pricing and model availability can change; verify them before use.
No web-search or tool call is enabled. Request, history, context, output, timeout, retry, and rate limits
bound provider usage.

Install dependencies:

```bash
pnpm install
uv sync --project backend --extra dev
```

Build the local knowledge index before starting the API:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli sync
```

First run can download the pinned `BAAI/bge-small-en-v1.5` embedding model. Embedding and retrieval
remain local and never call OpenAI or OpenRouter. Later offline runs can set
`EMBEDDING_LOCAL_FILES_ONLY=true` after model is cached.

Run each application in a separate terminal:

```bash
pnpm --dir frontend dev
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8012
```

Open the local chat at <http://localhost:5199>. Vite proxies `/api` to the backend on
`http://127.0.0.1:8012`.

The backend exposes `GET /health`, `GET /ready`, protected knowledge APIs, and `POST /api/v1/chat`.
Provider mode defaults to `disabled`; chat abstains without evidence and fails closed if evidence exists
while generation is unavailable.

### Provider alternatives

For direct OpenAI development instead of OpenRouter:

```text
CHAT_PROVIDER=openai
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=<your OpenAI API key>
CHAT_MODEL=gpt-5.6-luna
```

There is no provider fallback. Changing provider requires environment configuration only; frontend never
receives provider credentials.

### Knowledge management

Reviewed source files live in `backend/data/documents/`; allowlisted URL sources live in
`backend/data/sources.yaml`. From repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli sync
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli add-file backend/data/documents/SOURCE.md
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli add-url https://cadre.ai/PATH --source-id SOURCE_ID
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli remove SOURCE_ID
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli rebuild
PYTHONPATH=backend backend/.venv/bin/python -m app.ingestion.cli list
```

Public chat cannot ingest URLs. Runtime uploads and mutations require authenticated `/knowledge` access.

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

Opt-in live evaluation can consume provider credit:

```bash
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_live_chat.py \
  --max-cases 20 \
  --confirm-paid-api
```

The live runner only targets a local backend. Use repeatable `--case-id CASE_ID` options for a bounded
subset. Review answers and sources manually; HTTP 200 alone does not prove answer quality.

## Deployment

Deployment templates are provided for a non-Docker DigitalOcean setup:

- Nginx serves the static frontend and proxies backend routes.
- One systemd-managed Uvicorn worker listens only on `127.0.0.1:8010`.
- Releases are immutable under `/opt/cadre-ai/releases`.
- `current` and `previous` symlinks support atomic rollback.
- Persistent model/index directories live under `/var/lib/cadre-ai`.
- Production environment values live outside Git under `/etc/cadre-ai`.

See `deploy/digitalocean/README.md` for deployment, provider environment, rollback, and removal procedures.
Repository configuration never contains a real API key.

## Security

Never commit provider keys. Backend environment examples contain fictitious values only; browser code must never receive OpenAI or OpenRouter credentials.

Production loads one immutable, pinned embedding model revision from local files. Approved knowledge files
cannot replace model files. Dependency audits currently report no known vulnerabilities in production
Python or frontend packages.

## Current limitations

- Public DigitalOcean deployment remains intentionally unchanged with empty knowledge and provider mode
  `disabled`; public questions therefore abstain. Configure and run project locally for full behavior.
- Hybrid retrieval and the `0.7` score floor passed the versioned evaluations and 20-case local review.
  Retrieval scores remain ranking signals, not probabilities or guarantees of truth.
- Prompt delimiting and citation validation reduce but cannot eliminate model hallucination or injection.
- In-memory rate limits reset on restart and do not coordinate across workers or hosts.
- The MVP has no persisted chats, end-user authentication, OCR, actions, or distributed abuse controls.
- Production uses one backend worker and local filesystem state.

See `plan.md` for phased scope, architecture, risks, and acceptance criteria.
