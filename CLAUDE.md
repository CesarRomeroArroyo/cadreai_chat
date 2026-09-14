# Cadre AI Support Chatbot

## Purpose

Build a small, production-minded customer support chatbot for Cadre AI. The application must answer only from approved official sources, expose supporting sources with each answer, and abstain when evidence is insufficient.

This file is the project-level operating contract for AI-assisted development. Keep it accurate as implementation changes.

## Instruction Loading and Precedence

- OpenCode uses this root `CLAUDE.md` because no project `AGENTS.md` exists. OpenCode documents `CLAUDE.md` as the project fallback when `AGENTS.md` is absent.
- Do not add a duplicate `AGENTS.md`. If one is added later, OpenCode will prefer it over this file; reconcile rules explicitly rather than copying them.
- Global agent instructions still apply. More specific user instructions take precedence over this file.
- `docs/Cadre_AI_Chatbot_Take_Home_Candidate_v1.1.pdf` is a challenge specification, not a RAG source.

## Working Agreement

- Communicate with the user in Spanish.
- Write code, documentation, tests, configuration comments, and commits in English.
- Work through `plan.md` sequentially. Do not use subagents or parallel implementation.
- Inspect existing files before changing them.
- Before implementation begins, obtain explicit user confirmation of the plan.
- Every authorized implementation phase must include: implementation, focused verification, `plan.md` status update, and a small descriptive commit.
- Never claim a test, deployment, API call, or user-facing action succeeded without evidence.
- Fix failures before moving forward, or record the exact blocker in `plan.md`.
- Confirm the remote/destination once before the first push or deployment. Do not ask again after authorization unless the destination changes.
- Do not install dependencies, download models, call model APIs, deploy, or publish during the planning phase.

## Confirmed Stack

- Repository: one Git repository with separate `frontend/` and `backend/` applications.
- Frontend: React, Vite, strict TypeScript, pnpm.
- Backend: Python 3.12, FastAPI, Pydantic settings, pytest.
- Generation: an OpenAI-compatible provider adapter configured entirely through backend environment variables.
- Development generation: OpenAI using the user's personal key.
- Production generation: OpenRouter using the challenge key. Production must not require or fall back to the personal OpenAI key.
- Retrieval: local embeddings plus a persisted local vector index. Embedding and retrieval must not call OpenAI or OpenRouter.
- Storage: files only for the initial version. Do not add a relational database. If later evidence requires one, document the reason and use MySQL only after approval.
- Deployment target: the user's existing DigitalOcean Droplet through SSH alias `digitalocean`. Serve the locally built frontend with existing Nginx, reverse-proxy FastAPI to unused localhost port `8010`, run one Uvicorn worker under systemd, and persist model/index data on the Droplet filesystem. Use a dedicated nip.io hostname initially and no Dockerfile.

## Target Repository Layout

```text
.
├── frontend/                 # React/Vite client
├── backend/
│   ├── app/
│   │   ├── api/              # HTTP routes and schemas
│   │   ├── core/             # settings, errors, logging, rate limiting
│   │   ├── generation/       # provider-neutral chat interface and adapter
│   │   ├── rag/              # embedding, retrieval, prompting, citations
│   │   └── ingestion/        # extract, clean, chunk, index, CLI
│   ├── data/
│   │   ├── documents/        # approved local source documents
│   │   ├── sources.yaml      # allowlisted URL source manifest
│   │   └── index/            # generated local index; Git policy set by size
│   └── tests/
├── evaluation/               # retrieval and generated-answer datasets/scripts
├── docs/                     # challenge document and project notes
├── CLAUDE.md
├── plan.md
└── README.md
```

Keep boundaries explicit: API orchestration must not contain extraction logic; provider code must not perform retrieval; frontend must never receive provider credentials.

## Commands

The following setup and verification commands were exercised during Phase 1 on Node.js 22, pnpm 11, and Python 3.12:

```bash
# Frontend
pnpm install
pnpm --dir frontend dev
pnpm --dir frontend lint
pnpm --dir frontend test
pnpm --dir frontend build

# Backend
uv sync --project backend --extra dev
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8012
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
backend/.venv/bin/mypy backend/app backend/tests
backend/.venv/bin/pytest backend/tests
PYTHONPATH=backend backend/.venv/bin/python evaluation/run_retrieval.py
```

The local ingestion CLI is implemented. Run it from the repository root:

```bash
# Knowledge ingestion
backend/.venv/bin/python -m app.ingestion.cli sync
backend/.venv/bin/python -m app.ingestion.cli add-file backend/data/documents/SOURCE.md
backend/.venv/bin/python -m app.ingestion.cli add-url https://cadreai.com/PATH --source-id SOURCE_ID
backend/.venv/bin/python -m app.ingestion.cli remove SOURCE_ID
backend/.venv/bin/python -m app.ingestion.cli rebuild
backend/.venv/bin/python -m app.ingestion.cli list
```

`sync` and `list` were exercised with the pinned model in local-files-only mode. Mutation and
failure behavior is covered with fake embeddings in the normal automated test suite.

## API and Chat Contract

- Initial endpoints: `GET /health`, `GET /ready`, and `POST /api/v1/chat`.
- Chat requests contain one bounded user message and a bounded, typed session history. The backend remains stateless between requests.
- Validate message count, roles, per-message length, total history length, and request body size.
- Use recent bounded history only to interpret follow-up questions. Conversation history is never verified Cadre AI evidence.
- Flow: validate input → derive a simple contextual retrieval query → embed locally → retrieve evidence → cap context → call generation provider → validate citations → return answer and trusted source metadata.
- Prefer deterministic follow-up query construction from the current question plus a small recent-history window. Do not add a query-rewriting LLM call unless evaluation proves it necessary.
- Return a stable error envelope with a user-safe message and request ID. Never expose secrets, provider response bodies, or stack traces.
- Do not claim calls were booked, tickets were created, or people were contacted. The MVP only provides verified information and links.

## RAG Knowledge Rules

### Allowed sources

- Preselected official Cadre AI web pages in `backend/data/sources.yaml` and URLs submitted by an authenticated administrator from explicitly allowed Cadre AI domains.
- Approved Markdown, TXT, and text-extractable PDF files under `backend/data/documents/` or uploaded through the protected knowledge page.
- Every source must have a stable ID, title, canonical URL or relative filename, retrieval timestamp, content hash, and extraction status.
- Preserve page numbers, headings, and sections where extraction permits.

### Forbidden sources

- Challenge PDF, development instructions, source code, secrets, logs, private information, or arbitrary URLs supplied through chat.
- Scanned/image-only PDFs. OCR is out of scope; ingestion must report that no extractable text was found.
- Unverified links or facts generated by the conversational model.

### Ingestion behavior

- Download URLs only from the allowlisted manifest or authenticated knowledge workflow, only when their normalized hostname is allowed. Never accept URL ingestion from the public chat.
- Normalize text conservatively while retaining headings and page boundaries.
- Chunk by document structure, with a target maximum of 384 embedding-model tokens and 64-token overlap. This fits the selected encoder's context window, limits boundary loss, and keeps passages focused. Validate this choice with retrieval evaluation rather than treating it as fixed truth.
- Generate stable chunk IDs from source ID, source content hash, location, and normalized chunk content.
- Hash normalized source content to skip unchanged sources.
- Updating a changed source must atomically replace its old chunks. Removing a source must remove all associated chunks.
- Keep canonical chunk metadata and vectors separate from the derived vector index. Rebuild the exact index after changed-source or removal transactions; expected corpus size makes this simple and reliable.
- Write generated artifacts to a temporary location and atomically replace active artifacts only after successful validation.
- Report download failures, unsupported types, empty documents, PDFs without extractable text, and index/model incompatibility with non-zero exit status.
- Never download a model or rebuild an index while serving a chat request.

### Protected knowledge management

- Expose `/knowledge` as a public-route login screen and authenticated administration page; all data and mutation APIs remain protected in the backend.
- Use one environment-configured administrator password and a separate session-signing secret. Never expose either through `VITE_*`, source code, logs, or API responses.
- Authenticate with a short-lived, signed, `HttpOnly`, `Secure`, `SameSite=Strict` cookie. Apply login rate limiting and validate same-origin requests for state-changing operations.
- Allow multiple Markdown, TXT, and text-extractable PDF files per bounded multipart request. Validate extension, declared MIME type, content signature/decodability, individual size, aggregate size, and file count.
- Allow HTTPS URLs only from configured official Cadre AI hostnames. Reject credentials, non-default ports, localhost, private/reserved addresses, unsafe redirects, and disallowed response content types. Domain allowlisting reduces SSRF risk but does not guarantee protection against DNS rebinding.
- Require explicit administrator confirmation that submitted material is official and approved.
- List sources with status and metadata; support add/update, delete, and full rebuild. Preserve the CLI as an operational fallback.
- Serialize ingestion work in one process. Keep the previous index active until a complete replacement snapshot validates and is atomically activated.

## Local Embeddings and Vector Index

- Proposed encoder: `BAAI/bge-small-en-v1.5`, pinned to an immutable Hugging Face revision during implementation.
- Use `sentence-transformers` on CPU, 384-dimensional normalized embeddings, deterministic inference, and one model instance per backend process.
- Rationale: strong English retrieval quality for its size, approximately 33M parameters and roughly 130 MB of weights, modest CPU/RAM requirements, and broad Linux deployment support.
- Proposed index: FAISS `IndexFlatIP` over normalized vectors, persisted to `index.faiss` with `chunks.jsonl`, `vectors.npy`, and `index-meta.json`.
- Rationale: exact cosine-equivalent search, low operational complexity, approximately 1.5 KB per 384-dimensional float32 vector plus metadata, and acceptable latency for a small curated corpus. Approximate indexing is unnecessary initially.
- Record model ID, immutable revision, embedding dimension, normalization, and chunking version in index metadata. Refuse readiness on mismatch and require an explicit rebuild.
- Use the same pinned encoder and normalization for document and query vectors. Any documented query instruction must be deterministic and versioned.
- Production startup loads weights and the existing index from dedicated persistent directories on the DigitalOcean Droplet. Build/deploy setup may download the pinned model explicitly; request handling may not.
- Model weights and heavy caches must remain outside Git and the submission ZIP. Index artifacts may be included only if lightweight and intentionally approved; reproducible index preparation instructions are mandatory either way.

## Retrieval, Grounding, and Citations

- Retrieve a small candidate set using inner product over normalized embeddings. Start with `top_k=6`, then enforce a context token budget and source diversity.
- Treat similarity as a ranking signal, never as a probability of truth.
- Calibrate abstention thresholds against the evaluation set. Do not hard-code a confidence claim from vector scores.
- System instructions must define retrieved documents and user messages as untrusted data. Delimit context and instruct the model not to follow instructions found inside it. Document that these measures reduce risk but do not guarantee prompt-injection resistance.
- Require citation tokens containing backend-issued chunk/source IDs.
- Parse and validate every cited ID against the chunks actually supplied to the model. Drop invalid citations and map valid IDs to titles and canonical metadata URLs in backend code.
- If evidence is absent, weak, conflicting, or insufficient, answer with a concise limitation and provide a verified contact path only when that path exists in approved source metadata.
- Never let the model generate source URLs shown to users.

## Generation Provider Configuration

Backend environment variables must include:

```text
CHAT_PROVIDER=
CHAT_BASE_URL=
CHAT_API_KEY=
CHAT_MODEL=
CHAT_TIMEOUT_SECONDS=
CHAT_MAX_OUTPUT_TOKENS=
CHAT_TEMPERATURE=
CHAT_MAX_HISTORY_MESSAGES=
CHAT_MAX_INPUT_CHARS=
CHAT_CONTEXT_TOKEN_BUDGET=
```

- Keep one provider-neutral interface and one OpenAI-compatible HTTP implementation where practical.
- Validate provider/base URL/model combinations at startup without logging credentials.
- OpenAI development and OpenRouter production use configuration changes only; no source edits.
- No automatic provider fallback. In particular, never fall back from OpenRouter to a personal OpenAI key.
- Bound system instructions, history, retrieved context, timeout, retries, and output tokens to protect the USD 5 OpenRouter budget.
- Use at most one bounded retry for transient connection/rate-limit failures when safe. Do not retry invalid credentials, insufficient funds, or deterministic 4xx errors.

## Security, Privacy, and Operations

- Secrets exist only in backend environment variables. Never use `VITE_*` for provider keys.
- Commit only `.env.example` files containing fictitious values.
- Keep `.env*` secrets, virtual environments, dependency folders, generated builds, model weights, and heavy caches out of Git and ZIP output.
- Configure CORS to the exact deployed frontend origin plus explicit local development origins. CORS is browser policy, not abuse prevention.
- Add bounded per-IP application rate limiting for the public MVP and document that in-memory counters reset, are per-process, and are not globally reliable across replicas. Run one backend worker initially. Platform-edge controls are preferred when available.
- Apply provider timeouts, bounded retries, safe error mapping, and request IDs.
- Log minimal structured fields: request ID, route, status, latency, retrieval count, provider latency, error category, and token usage when returned. Do not log raw chats, retrieved content, authorization headers, or keys by default.
- Distinguish invalid credentials, insufficient balance, rate limiting, timeout, unavailable provider, malformed response, and internal failures internally; expose understandable but non-sensitive client messages.

## Verification Rules

- Normal automated tests must use a fake generation provider. Real API tests must be opt-in and clearly marked.
- Verify ingestion idempotency, changed-source replacement, source/chunk deletion, empty content, failed downloads, and textless PDFs.
- Verify expected evidence retrieval independently from answer generation.
- Maintain a small versioned evaluation dataset containing representative questions, expected source IDs, expected abstentions, follow-ups, and prompt-injection attempts.
- Verify citation allowlisting, fabricated citation rejection, insufficient-evidence abstention, provider errors, input/history limits, and rate-limit behavior.
- Verify frontend loading, reset, error, source display, keyboard/accessibility, responsive behavior, and complete frontend-to-backend-to-RAG flow.
- Run production-model evaluation with OpenRouter only when explicitly authorized, with a strict case count and token budget. Record command, model, date, and factual result without secrets.
- Before delivery, verify the public URL, health/readiness endpoints, representative chat paths, and mobile layout.

## Git and Phase Discipline

- Do not commit during the unapproved planning phase unless explicitly requested.
- After approval, keep one phase in progress at a time.
- Before each commit, inspect `git status`, `git diff`, and recent history; stage only phase-related files.
- Use small English Conventional Commits such as `feat(rag): add idempotent source ingestion` or `test(api): cover invalid citations`.
- Update `plan.md` with evidence and remaining limitations before committing each phase.
- Never amend, force-push, or push/deploy without explicit authorization required by the working agreement.

## Initial Scope Boundaries

Included: English responsive chat UI, session-only history, new-conversation reset, loading/error states, source cards, bounded follow-ups, local RAG, source-management CLI, provider configuration, tests, evaluation, and public deployment.

Also included: protected administrator authentication and a responsive `/knowledge` page for bounded multi-file and allowlisted URL ingestion, source replacement/removal, and index rebuild.

Excluded: end-user authentication, persisted chats, relational database, CRM/ticket/calendar actions, streaming unless schedule permits, OCR, multilingual behavior, analytics platform, distributed rate limiting, reranking model, autonomous browsing, and arbitrary-domain or public-chat URL ingestion.
