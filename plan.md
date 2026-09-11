# Cadre AI Support Chatbot Implementation Plan

## Status

- Current stage: Phase 4 in progress
- Implementation authorization: Phases 1–4 authorized; push to `origin/master` authorized after each logical commit
- Dependencies installed: yes, frontend, backend development, and production dependencies
- Models downloaded: yes, pinned embedding model on the production host
- External APIs called: Hugging Face model download only; no generation-provider API calls
- Deployment created: yes, reversible Phase 3 deployment on DigitalOcean
- Public URL: `https://cadre-ai.164.90.135.146.nip.io`
- Last updated: 2026-09-11
- Deployment target: SSH alias `digitalocean`; initial public hostname `cadre-ai.<droplet-ip>.nip.io`

## Inputs Reviewed

- Repository: initial commit containing only a one-line `README.md`; challenge PDF is currently untracked.
- Challenge: `docs/Cadre_AI_Chatbot_Take_Home_Candidate_v1.1.pdf`, eight pages, text extractable.
- Project instruction files: no root `AGENTS.md`, `CLAUDE.md`, or prior `plan.md` existed before this planning stage.
- OpenCode rule behavior: root `CLAUDE.md` is loaded as a compatibility fallback when no project `AGENTS.md` exists. Adding both would make `AGENTS.md` win and risk divergence, so this plan keeps only `CLAUDE.md`.

## Challenge Requirements Extracted from the PDF

### Product and scenarios

- Build a plausible customer support chatbot for Cadre AI.
- Cover what Cadre AI does, industries served, strategy-call booking, client portal access, AI Maturity Index, LLM selection, data security, and unknown-question redirection.
- Make deliberate scope and knowledge-boundary decisions.

### Required deliverables

- Publicly accessible deployed URL delivered at least one full business day before review.
- Complete project ZIP uploaded through the recruiting submission link.
- Root `CLAUDE.md` and `plan.md`.
- Git history included in the ZIP through the `.git` directory.
- Dependency/build folders excluded, including `node_modules`, `dist`, `build`, and virtual environments.

### Evaluation emphasis

- AI-assisted workflow and context management: 30%.
- system design and architecture: 25%.
- speed and scope control: 20%.
- code quality and verification: 15%.
- communication and reasoning: 10%.
- Review includes live demo, architecture, AI workflow, code deep dive, and trade-offs.

### Process guidance

- Plan before coding, deploy early, commit frequently, test as work proceeds, cut scope, and make trade-offs explicit.
- Recommended build budget is 4–6 hours, but quality and judgment matter more than a hard limit.

## Conflicts and Resolutions

1. **Subagents:** PDF recommends subagents for independent work and evaluates Claude Code workflow. User explicitly requires sequential work without subagents or parallel work. Resolution: follow direct user instruction; record this constraint so absence of subagent usage is explainable during review.
2. **Tool emphasis:** PDF says Claude Code is the primary evaluated tool. Current user explicitly asks that OpenCode load project instructions. Resolution: use root `CLAUDE.md`, which is compatible with both Claude Code and OpenCode; do not add a competing `AGENTS.md`. Risk: work performed outside Claude Code may not demonstrate the PDF's highest-weighted dimension as strongly.
3. **Stack freedom:** PDF allows any deployable stack; user narrows this to React/Vite/strict TypeScript and Python/FastAPI with local RAG. No true contradiction; user constraint wins.
4. **Knowledge claims:** PDF lists common topics including pricing and case studies, but user forbids invented prices, links, policies, cases, or procedures. Resolution: answer only when approved official sources support the claim; otherwise abstain.

No other material contradiction was found.

## Proposed MVP Architecture

```text
Browser (React/Vite)
  -> POST /api/v1/chat with current message + bounded session history
FastAPI
  -> validation and per-IP in-memory rate limit
  -> deterministic follow-up retrieval query
  -> singleton local embedding service
  -> FAISS exact vector search + metadata lookup
  -> bounded, delimited evidence context
  -> provider-neutral generation service
       development: OpenAI
       production: OpenRouter
  -> backend citation validation and trusted URL mapping
  -> answer + validated sources
```

### Frontend

- React with Vite and strict TypeScript.
- Session state held in memory; browser refresh may clear it.
- English single-page chat with empty, loading, success, abstention, and recoverable error states.
- Message composer, submit behavior, disabled/loading affordance, new-conversation reset, and source cards attached to assistant responses.
- Responsive layout and basic keyboard/screen-reader support.
- No key, direct provider request, authentication, chat persistence, admin UI, or CRM action.

### Backend

- FastAPI application with typed request/response schemas.
- Stateless chat endpoint plus liveness/readiness endpoints.
- Clear modules for API, configuration, generation, RAG, ingestion, and shared errors/logging.
- OpenAI-compatible asynchronous generation client configured through environment variables.
- One process-level embedding model instance and one loaded immutable index snapshot.
- File-backed knowledge artifacts; no relational database.

### Initial API shape

- `GET /health`: process liveness; does not imply model/index readiness.
- `GET /ready`: confirms compatible embedding model and index are loaded.
- `POST /api/v1/chat`: accepts bounded message/history and returns `answer`, validated `sources`, and `request_id`.

## Local Embedding and Index Decision

### Encoder: `BAAI/bge-small-en-v1.5`

- Pin an immutable model revision, not only a mutable model name.
- 384-dimensional embeddings, about 33M parameters and roughly 130 MB of weights.
- English-focused retrieval quality is suitable for the initial English interface and Cadre corpus.
- CPU inference and memory needs fit a small persistent backend service better than larger encoders.
- Normalize document and query vectors; version any deterministic query prefix in index metadata.
- Load once per process. Never download from a chat request.

### Index: FAISS `IndexFlatIP`

- Exact inner-product search over normalized vectors, equivalent to cosine ranking.
- About 1.5 KB of raw float32 vector memory per chunk at 384 dimensions, excluding metadata.
- Better MVP trade-off than HNSW: exact results, deterministic behavior, easy rebuilding, and no approximate-search tuning for a small corpus.
- Persist `index.faiss`, `vectors.npy`, `chunks.jsonl`, and `index-meta.json`.
- Rebuild derived index atomically after source changes or deletions. This favors correctness and simple idempotency over unnecessary incremental complexity.

### Restart and deployment behavior

- Dedicated DigitalOcean host directories store generated knowledge artifacts and the pinned model cache outside Git, proposed as `/var/lib/cadre-ai/index` and `/var/lib/cadre-ai/models`.
- Deployment/bootstrap step explicitly downloads the pinned model if absent and prepares or restores the index before the systemd service becomes ready.
- Backend startup loads existing weights and index; readiness fails if artifacts are absent or incompatible.
- Chat requests never trigger model downloads, URL downloads, ingestion, or index rebuilding.
- Model weights and heavy caches stay out of Git and ZIP. README will provide reproducible preparation commands.

## Ingestion Strategy

### Inputs

- URL entries from `backend/data/sources.yaml`, each with an explicit stable source ID and approved official Cadre AI URL.
- Authenticated administrator URL submissions restricted to configured official Cadre AI hostnames; each submission requires explicit approval confirmation.
- Markdown, TXT, and text-extractable PDF files from `backend/data/documents/` or the protected multi-file upload form; stable file IDs derive from normalized filenames while hashes detect unchanged or duplicate content.
- Challenge PDF and development files are explicitly excluded.

### Pipeline

1. Resolve only manifest allowlist URLs and allowed local file extensions.
2. Download URLs with timeout, bounded retries, content-size cap, and explicit user agent.
3. Extract text; retain canonical title, URL/path, retrieval date, page, heading, and section metadata where available.
4. Normalize whitespace and boilerplate conservatively without erasing document structure.
5. Compute normalized source hash; skip unchanged sources.
6. Split on page/heading/paragraph boundaries up to 384 encoder tokens with 64-token overlap.
7. Generate local normalized embeddings in bounded batches.
8. Replace changed source records in a temporary artifact set; unchanged source records remain untouched.
9. Build and validate a complete FAISS index, then atomically swap active files.
10. Emit a concise report and non-zero exit status for failed downloads, unsupported/empty documents, textless PDFs, duplicate source IDs, or incompatible metadata.

### CLI contract

- `sync`: ingest all approved files and manifest URLs, skipping unchanged sources.
- `add-file PATH`: ingest or update one file inside the approved documents directory.
- `add-url URL [--source-id ID] [--title TITLE]`: ingest or update one allowlisted HTTPS source.
- `remove SOURCE_ID`: remove source and all chunks, then rebuild derived index.
- `rebuild`: regenerate every embedding and index artifact, required after incompatible model/config changes.
- `list`: emit current source metadata as JSON Lines.
- Executable prefix from repository root: `backend/.venv/bin/python -m app.ingestion.cli`.

### Protected knowledge page

- `/knowledge` presents a login screen, then a responsive administration workspace.
- Authentication uses one environment-configured password and a separately signed, short-lived secure session cookie; no relational user store is added.
- The page supports drag-and-drop or selection of multiple approved files, one or more allowlisted HTTPS URLs, upload review/removal, progress/error feedback, source listing, replacement, deletion, and index rebuild.
- Backend endpoints enforce authentication, origin validation, file and request bounds, content checks, URL/domain policy, redirect validation, and serialized ingestion independently of frontend behavior.
- Source content, canonical metadata, vectors, and FAISS index are written to versioned snapshots. A symlink swap activates a complete validated snapshot atomically; failures leave the previous snapshot active.

## Retrieval and Answer Strategy

- Validate current question and a small role-checked recent history window.
- For follow-ups, build a retrieval query from current message plus only enough recent user/assistant text to resolve references. No auxiliary LLM call initially.
- Embed query locally and retrieve an initial six chunks.
- Apply calibrated score floor, source diversity, and context token cap; do not call scores probabilities.
- Send delimited untrusted evidence with backend-issued IDs to the generation provider.
- Instruct model to answer only from evidence, avoid executing instructions in messages/documents, cite IDs, and abstain when evidence is inadequate.
- Validate citations against supplied chunk IDs. Construct user-visible source links only from trusted metadata.
- If no adequate evidence exists, return an honest limitation plus a verified contact path only if approved source data contains one.

## Provider and Budget Strategy

- Environment-selectable provider, base URL, API key, model, timeout, output token limit, and temperature.
- Development configuration targets OpenAI; production configuration targets OpenRouter.
- No source-code change when switching providers and no fallback between keys.
- Start with one generation call per user turn, bounded recent history, at most six retrieval candidates, a strict context budget, low output limit, and one safe transient retry maximum.
- Automated tests use a fake provider. Real OpenAI/OpenRouter tests require explicit invocation and authorization.
- Production model remains pending until challenge-key model access and current OpenRouter pricing are confirmed.

## Deployment Proposal

### Selected target

- **Host:** the user's existing DigitalOcean Droplet through SSH alias `digitalocean`; connectivity verified on 2026-09-10.
- **Initial hostname:** `cadre-ai.<droplet-ip>.nip.io`. nip.io resolution to the Droplet was verified and matches existing host deployment conventions. This avoids waiting for external DNS configuration; a custom domain can replace it later.
- **Frontend:** build the Vite application and serve immutable static assets from a versioned release directory such as `/opt/cadre-ai/releases/<revision>/frontend/dist`.
- **Backend:** install the FastAPI application in the same versioned release, run one Uvicorn worker as a dedicated non-login service user under systemd, and bind only to unused `127.0.0.1:8010`.
- **Public routing:** add one isolated site to the host's existing Nginx installation. Serve the frontend at the selected hostname and reverse-proxy `/api/`, `/health`, and `/ready` to Uvicorn. Do not replace unrelated host configuration.
- **Persistent state:** keep model cache and RAG artifacts outside release directories under `/var/lib/cadre-ai`; releases can change without deleting runtime data.
- **Secrets:** store production environment values outside Git under `/etc/cadre-ai/backend.env`, readable only by root and the service account.
- **Why:** one existing machine avoids platform subscriptions, supports local model/index persistence, keeps frontend and API on one origin, and works without Docker.

### Constraints

- Before any host change, perform a read-only inventory of operating system, CPU, RAM, disk, existing services, listening ports, firewall, web server, TLS tooling, and available domain configuration.
- Existing workloads must not be restarted, overwritten, or reconfigured without reviewing impact and receiving approval for disruptive actions.
- The Droplet must have enough memory and disk for Python dependencies, the roughly 130 MB embedding model, index artifacts, and process overhead; exact capacity remains unverified.
- HTTPS requires a confirmed domain/subdomain and DNS mapping, plus a compatible existing certificate workflow or an approved certificate setup.
- Deployment should use versioned releases and an atomic `current` symlink so rollback does not require rebuilding files in place.
- One-worker in-memory rate limiting is only an MVP control; it resets on restart and does not coordinate across replicas.
- Source updates are available through both the local CLI and the protected administration UI.
- Host alias, initial nip.io hostname, deployment paths, and localhost port are selected. Permission for the listed web-server/systemd changes was confirmed before first deployment.

### Read-only host audit — 2026-09-10

- Connectivity to SSH alias `digitalocean` succeeded; raw host details remain outside repository documentation.
- Host runs Ubuntu 22.04 LTS on x86-64 with 4 vCPUs, 7.8 GiB RAM, 4 GiB swap, and approximately 47 GiB free disk.
- No failed systemd units were present during inspection.
- Existing Nginx 1.18 serves multiple applications on ports 80/443; configuration test passed before any Cadre AI changes.
- Certbot and its renewal timer are installed and active. Existing nip.io certificates demonstrate a compatible HTTPS path.
- UFW is active. Cadre AI needs no new public application port because Nginx will proxy to localhost.
- Port `8010` was unused during inspection and is selected for Uvicorn. Recheck immediately before deployment to avoid a race.
- Host Python is 3.10 and no global Node executable is available. Build frontend locally; provision isolated Python 3.12 for backend instead of changing system Python.
- MySQL, Redis, PM2, and several unrelated applications already run on the host. Cadre AI will not use or modify them.
- Production capacity remains adequate after model loading; the Phase 3 service uses approximately 345 MiB.

## Sequential Phases

### Phase 0 — Planning and authorization

**Status:** completed

Deliverables:
- Review repository and challenge PDF.
- Create `CLAUDE.md` and `plan.md` drafts.
- Record architecture, retrieval, ingestion, deployment, risks, and pending decisions.

Acceptance:
- No dependencies, model downloads, API calls, app implementation, commits, or deployment performed.
- User reviewed conflicts and explicitly authorized Phase 1 on 2026-09-10.

### Phase 1 — Repository foundation

**Status:** completed

Deliverables:
- Scaffold strict React/Vite frontend and FastAPI backend.
- Add dependency manifests, lint/type/test configuration, `.gitignore`, fictitious `.env.example`, and initial README setup.
- Add health endpoint and basic frontend shell.
- Replace provisional commands in `CLAUDE.md` with commands actually run.

Acceptance:
- Frontend lint, type check/test baseline, and production build pass.
- Backend import, lint/type checks, and baseline tests pass.
- No secrets or generated dependency/build folders tracked.
- `plan.md` updated and phase committed.

Verification evidence recorded on 2026-09-10:
- `pnpm install`: completed and generated the workspace lockfile. A transitive `protobufjs` install script is explicitly denied because frontend lint, test, and build do not require it.
- `pnpm --dir frontend lint`: passed.
- `pnpm --dir frontend test`: one test passed; no external API calls.
- `pnpm --dir frontend build`: strict TypeScript and Vite production build passed.
- `backend/.venv/bin/ruff check backend`: passed.
- `backend/.venv/bin/ruff format --check backend`: passed for eight Python files.
- `backend/.venv/bin/mypy backend/app backend/tests`: strict type check passed for eight Python files.
- `backend/.venv/bin/pytest backend/tests`: one test passed without warnings or API calls.
- Local Uvicorn smoke test: `GET /health` returned `{"status":"ok"}`.
- Browser accessibility snapshot exposed the expected heading, message, labeled disabled composer, and disabled send button.
- Visual checks completed at desktop and 375 × 812 mobile viewports; no browser console warnings or errors appeared.
- React Doctor scanned five frontend files and reported 100/100 with no findings.
- No model download, generation-provider call, deployment, push, or paid API usage occurred.

### Phase 2 — Early public deployment skeleton

**Status:** completed

Deliverables:
- Confirm the exact DigitalOcean host, domain/subdomain, and allowed configuration changes.
- Audit host capacity and existing services read-only before modifying it.
- Prepare a versioned release without Docker, a dedicated service user, systemd unit, external environment file, persistent data directories, and safe web-server routing.
- Deploy the static frontend and health-only backend skeleton without provider credentials.
- Keep frontend and API on one origin where possible; otherwise configure exact production CORS.
- Record deployment and rollback commands, URLs, ownership, and host constraints without exposing secrets.

Acceptance:
- Existing host services remain healthy and their configuration is preserved.
- Public HTTPS frontend loads at the confirmed domain.
- Public backend health endpoint responds through the reverse proxy while Uvicorn remains bound to localhost.
- systemd restarts the backend successfully and logs contain no secrets.
- Static release and service rollback procedure is documented and checked.
- No claim of functional chat yet.
- `plan.md` updated and phase committed.

Verification evidence recorded on 2026-09-11:
- Local frontend lint, Vitest, strict TypeScript build, backend Ruff, mypy, and pytest all passed immediately before packaging; no paid APIs were called.
- Added committed systemd, Nginx, environment, rollback, and removal templates plus a deployment runbook.
- Installed pinned `uv` 0.10.9 and isolated CPython 3.12.13 under `/opt/cadre-ai`; system Python remained unchanged. The upstream installer reported no checksum available, so version pinning and HTTPS reduced but did not eliminate installer supply-chain risk.
- Deployed two immutable releases. Active and previous symlinks point to separate release directories.
- Uvicorn runs as dedicated non-login user `cadreai`, one worker, bound only to `127.0.0.1:8010`, under a hardened systemd unit.
- Nginx configuration validation passed before reload; an isolated Cadre AI site serves frontend and proxies backend health/API paths.
- Let's Encrypt certificate was issued successfully for the nip.io hostname and expires on 2026-12-10; existing Certbot renewal timer is active.
- HTTP redirects to HTTPS; public frontend and `GET /health` return HTTP 200 over HTTPS.
- Immediate health probing after one restart raced process startup once; bounded polling then verified successful restart behavior.
- Browser accessibility tree and visual layout were checked publicly at mobile and desktop sizes; browser console contained no warnings or errors.
- Final Lighthouse navigation audit scored 100 accessibility, 100 best practices, and 100 SEO with zero failed audits.
- Rollback command switched to the previous release, passed health, then switched back to the latest release and passed public health.
- Existing Nginx, MySQL, Redis, PM2, and App Cafeteria services remained active; systemd reported no failed units.
- Temporary upload and smoke-test files were removed. Persistent data, both releases, certificate, and rollback path remain intact.

### Phase 3 — Idempotent ingestion and local index

**Status:** completed

Core ingestion, protected API/UI, and production deployment completed on 2026-09-11.

Deliverables:
- Approved source manifest and document directory rules.
- Extractors for HTML, Markdown, TXT, and text PDFs.
- Cleaning, metadata preservation, token-aware chunking, local embeddings, persistent FAISS artifacts, and CLI operations.
- Model/config compatibility metadata and atomic artifact replacement.
- Environment-backed administrator authentication, secure session cookie, login rate limiting, and mutation-origin validation.
- Protected knowledge APIs and `/knowledge` page for multiple files, allowlisted URLs, source listing, replacement/removal, and rebuild.

Acceptance:
- Unchanged sync creates no duplicate source/chunk records.
- Changed source replaces obsolete chunks.
- Removal deletes every source chunk.
- Rebuild works from approved sources.
- Download failure, empty file, and textless PDF produce explicit errors.
- Challenge PDF cannot enter knowledge index.
- Unauthenticated source reads and mutations are rejected.
- File count, per-file size, aggregate size, extension, MIME, signature/decodability, and approval confirmation are validated in the backend.
- URL ingestion accepts only configured HTTPS Cadre AI hosts and rejects unsafe ports, addresses, redirects, and response types.
- Multiple-file upload reports per-source success, unchanged, duplicate, or error status without corrupting the active index.
- Administrator can list, replace, delete, and rebuild sources through the responsive web page.
- Normal automated tests use fake embeddings and local fixtures; no generation-provider API is called.
- `plan.md` updated and phase committed.

Core ingestion checkpoint evidence recorded on 2026-09-11:
- Added strict Markdown, TXT, text-PDF, HTML, and web-content extraction with challenge-content exclusion.
- Added stable source/content/chunk identities, token-window chunking at configurable 384/64 defaults, normalized local embeddings, exact FAISS inner-product index, canonical metadata, and persisted source content.
- Added immutable snapshots with validated artifacts and atomic symlink activation; failed generation preserves the active snapshot.
- Added HTTPS host allowlisting, credential/port rejection, public-address checks, bounded redirects, response-size limits, and explicit content-type handling. DNS rebinding remains a documented residual risk.
- Pinned `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; real local smoke produced one normalized 384-dimensional vector and a one-source/one-chunk FAISS snapshot.
- Pinned CPU-only Torch for Linux deployment to avoid CUDA dependency downloads while retaining the native macOS wheel for development.
- Real threadpool integration initially hung during embedding on macOS. Explicit bounded Torch intra-op and inter-op configuration resolved it; repeated cross-thread model load, extraction, embedding, FAISS activation, and source listing completed successfully.
- `uv lock --project backend` and `uv sync --project backend --extra dev`: passed.
- `backend/.venv/bin/ruff check backend`: passed.
- `backend/.venv/bin/ruff format --check backend`: passed for 26 Python files.
- `backend/.venv/bin/mypy backend/app backend/tests`: strict check passed for 26 Python files.
- `backend/.venv/bin/pytest backend/tests`: 17 tests passed; fake embeddings used by automated tests and no generation-provider API was called.
- CLI help, empty-manifest `sync`, and empty-index `list` were exercised using cached model files with `EMBEDDING_LOCAL_FILES_ONLY=true`.
- Remaining Phase 3 scope: bounded multi-file validation, administrator authentication/session/origin controls, protected knowledge APIs, responsive `/knowledge` UI, integration tests, and deployment.

Protected knowledge API checkpoint evidence recorded on 2026-09-11:
- Added fail-closed environment-backed administrator credentials and independent HMAC-SHA256 session signing; weak or missing configuration returns service unavailable without exposing configured values.
- Added short-lived `HttpOnly`, configurable `Secure`, `SameSite=Strict` cookies scoped to knowledge APIs, constant-time password verification, bounded per-client login attempts, and bounded limiter tracking memory.
- Added exact configured-origin validation for login and every mutation plus credentialed exact-origin CORS support.
- Added authenticated session/source reads, multi-file ingestion, batch URL ingestion, source deletion, rebuild, and logout endpoints.
- Added backend-enforced request, file-count, per-file, aggregate-upload, URL-count, URL-response, field-length, MIME, decodability, and approval-confirmation bounds. Streamed/chunked request bytes are counted independently of `Content-Length`.
- Mixed batch results preserve submitted order and report per-source indexed, updated, unchanged, duplicate, or error state; source mutations execute off the event loop and reuse one process-level service lock.
- Updated deployment templates for persistent model/index paths, local-files-only startup, administrator secrets, credential cookies, and a 21 MiB Nginx request cap. No deployment occurred in this checkpoint.
- `backend/.venv/bin/ruff check backend` and `backend/.venv/bin/ruff format --check backend`: passed for 31 Python files.
- `backend/.venv/bin/mypy backend/app backend/tests`: strict check passed for 31 Python files.
- `backend/.venv/bin/pytest backend/tests`: 29 tests passed without warnings or external API calls.
- Remaining Phase 3 scope: responsive `/knowledge` UI, frontend/API integration tests, full regression verification, credential generation on the Droplet, model/index provisioning, deployment, and public validation.

Protected knowledge UI checkpoint evidence recorded on 2026-09-11:
- Added lazy-loaded `/knowledge` routing without adding a routing dependency; public chat shell remains the default route and local Vite development proxies `/api` to FastAPI.
- Added responsive English login and administration experiences using the existing Cadre AI visual language, with file drag-and-drop plus keyboard-accessible selection, URL batching, explicit official-source confirmation, ordered operation results, source metadata, two-step deletion, rebuild, and logout.
- Password input permits paste and password managers. Errors use a focused `role="alert"`; status updates use live regions; forms have explicit labels, visible focus, disabled states, and reduced-motion handling.
- Frontend API client uses same-origin credentialed requests and contains no administrator or provider secrets.
- `pnpm --dir frontend lint`: passed without warnings.
- `pnpm --dir frontend test`: four tests passed across two files, covering support-shell isolation, unauthenticated login, focused login errors, approved upload, operation feedback, and source refresh.
- `pnpm --dir frontend build`: strict TypeScript and Vite production build passed.
- React Doctor full scan scored 100/100 with no findings.
- Local desktop and 375 px mobile visual checks passed for login and populated console states. Accessibility snapshots exposed expected headings, labels, pressed/disabled states, live feedback, and confirmation controls; Lighthouse snapshot scored 100 accessibility, 100 best practices, and 100 SEO.
- Real browser-to-Vite-to-FastAPI integration used the cached pinned BGE model and a temporary index: login, authenticated source listing, TXT upload, embedding/FAISS activation, source refresh, rebuild, two-step deletion, and logout all succeeded. Final browser console contained no warnings or errors, and backend remained healthy.
- Temporary source/index and local processes were removed or stopped. No production deployment or generation-provider API call occurred.
- Remaining Phase 3 scope at this checkpoint was full regression verification, production credential generation, model cache provisioning, deployment, public API/UI validation, and final status update.

Production deployment evidence recorded on 2026-09-11:
- Final regression passed: `uv lock --check --project backend`, Ruff, Ruff formatting, strict mypy, 29 backend tests, frontend lint, four frontend tests, strict TypeScript/Vite build, and React Doctor 100/100. Automated verification used fake embeddings where intended and made no generation-provider API calls.
- Generated independent administrator password and session-signing secrets directly on the Droplet. `/etc/cadre-ai/backend.env` remains `0640 root:cadreai`; credential values were not printed or committed.
- Downloaded the exact pinned `BAAI/bge-small-en-v1.5` revision into `/var/lib/cadre-ai/models` as `cadreai`; a subsequent local-files-only load returned dimension 384.
- Deployed immutable release `/opt/cadre-ai/releases/20260911162342-b04d4c2`; `previous` points to `/opt/cadre-ai/releases/20260911161904-edc6238`. Uvicorn remains one worker on `127.0.0.1:8010` and uses approximately 345 MiB after loading the embedding model.
- Isolated release smoke tests on `127.0.0.1:8011` passed before activation. Public HTTPS `GET /health`, `/knowledge`, and unauthenticated session protection passed after activation.
- Public authenticated API smoke covered secure-cookie attributes, login, TXT upload, one-chunk embedding/index activation, source listing, full rebuild, deletion, logout, and post-logout rejection. Temporary source and request files were removed.
- Increased only the Cadre AI Nginx `client_max_body_size` directive from `64k` to `21m`, preserved Certbot directives, passed `nginx -t`, and verified a 70 KB request reached backend validation instead of being rejected by Nginx.
- Production rollback exposed a real cold-start timing defect: the original 10-second health window was too short for model loading. Commit `f1e1903` extends it to 60 seconds; rollback from latest to previous and back to latest then passed with health checks.
- Public mobile Lighthouse scored 100 accessibility, 96 best practices, and 100 SEO. The only failed audit is the expected unauthenticated `401` session probe used to render the login screen; the prior accessible-name mismatch was fixed in `b04d4c2`.
- Nginx and `cadre-ai.service` are active, no systemd units are failed, recent service logs contain no warnings, and temporary deployment archives were removed.
- `GET /ready`, retrieval, chat, and generation remain intentionally pending for Phase 4. Public `/ready` currently returns 404 and no functional chat claim is made.

### Phase 4 — Retrieval, provider adapter, and grounded chat API

**Status:** in progress

Deliverables:
- Singleton embedding/index lifecycle and readiness behavior.
- Retrieval query handling for direct and follow-up questions.
- OpenAI-compatible configurable generation adapter with fake test implementation.
- Bounded prompts/history/context/output, abstention behavior, citation parsing/validation, safe errors, timeout/retry policy, structured minimal logs, and MVP rate limit.

Acceptance:
- Expected evidence is retrieved for representative questions.
- Missing evidence abstains.
- Invalid model-produced citations never reach clients.
- Source URLs come only from metadata.
- Prompt-injection tests demonstrate intended handling without claiming guaranteed prevention.
- OpenAI/OpenRouter switch requires environment changes only.
- Provider error categories and input limits are tested.
- `plan.md` updated and phase committed.

Retrieval/readiness checkpoint evidence recorded on 2026-09-11:
- Added a process-level retrieval service that keeps the active immutable FAISS snapshot loaded and refreshes only when the atomic `current` snapshot symlink changes.
- Added deterministic BGE query encoding, finite vector validation, exact inner-product search, bounded `top_k`, and per-source diversity.
- Added `GET /ready`; it returns 200 only when a compatible active snapshot is loaded and returns a safe 503 for an absent or incompatible snapshot. A valid empty snapshot remains ready.
- Serialized SentenceTransformer inference through one process-level lock so chat queries cannot race ingestion model calls.
- Focused retrieval, readiness, ingestion regression, Ruff, formatting, and strict mypy checks passed: 12 tests and 33 typed source files.
- No external model or generation-provider API was called during this checkpoint.

Grounded chat API checkpoint evidence recorded on 2026-09-11:
- Added one provider-neutral generation interface and one asynchronous OpenAI-compatible adapter. OpenAI and OpenRouter differ only through validated backend settings; there is no automatic fallback.
- Added fail-closed `disabled` provider mode for deployments without approved generation credentials. Provider configuration is validated at startup without making a provider request or logging keys.
- Added bounded timeout, output tokens, temperature, and one transient retry. Invalid credentials, insufficient funds, provider rate limiting, timeout, unavailability, rejected requests, and malformed responses remain distinct internally while clients receive safe messages.
- Added `POST /api/v1/chat` with bounded typed history, deterministic follow-up retrieval queries, request-body limits, per-IP in-memory rate limiting, safe request IDs, stable error envelopes, and minimal structured logs that exclude raw messages and retrieved content.
- Added bounded context selection and explicit instructions treating documents and user messages as untrusted data. Backend citation parsing allows only supplied chunk IDs, maps URLs from trusted source metadata, removes fabricated citations and model-generated URLs, and abstains when evidence or valid citations are absent.
- Focused provider, follow-up query, chat API, and readiness tests passed: 18 tests. Ruff, formatting, and strict mypy passed for 47 source files.
- All provider behavior used `httpx.MockTransport` or a fake provider; no OpenAI/OpenRouter request or paid API call occurred.

Retrieval evaluation checkpoint evidence recorded on 2026-09-11:
- Added a versioned seven-case dataset with synthetic test-only sources covering services, AI maturity, portal access, a contextual follow-up, unsupported pricing, an unrelated question, and prompt injection. Evaluation fixtures remain outside production knowledge paths.
- Added a reproducible local-only runner that creates a temporary index, uses the pinned cached BGE revision, reports source IDs and top scores, and exits non-zero on expectation failures.
- Initial `0.4` score floor passed 5/7 and incorrectly accepted unsupported pricing at `0.6290` and prompt injection at `0.4198`. A provisional `0.7` floor passed 7/7; positive top scores ranged from `0.8248` to `0.8492`.
- Scores are recorded only as ranking/filter signals, never probabilities or factual-confidence claims. The provisional floor must be recalibrated against approved production content during Phase 6.
- Full local verification passed: lock check, Ruff, formatting, strict mypy, 49 backend tests, frontend lint, four frontend tests, strict TypeScript/Vite build, and 7/7 real-model retrieval cases.
- Evaluation loaded model files with `local_files_only=True`; no model download, generation-provider request, or paid API call occurred.

### Phase 5 — Chat interface and integrated flow

**Status:** pending

Deliverables:
- Responsive English chat UI with session history, composer, submit, reset, loading, errors, abstention messaging, and per-response sources.
- Typed API client and complete browser-to-backend integration.
- Accessible focus, labels, keyboard submission, and readable mobile behavior.

Acceptance:
- Representative direct, follow-up, abstention, reset, loading, error, and citation flows work with fake provider responses.
- Frontend does not contain provider secrets or direct provider calls.
- Responsive and accessibility checks pass at agreed MVP level.
- `plan.md` updated and phase committed.

### Phase 6 — Evaluation and hardening

**Status:** pending

Deliverables:
- Versioned retrieval dataset with expected sources and abstentions.
- Separate retrieval evaluation and generated-answer evaluation.
- Integration/E2E coverage for frontend, backend, and RAG.
- Security/error review, budget controls, README architecture and limitations.

Acceptance:
- Ingestion, retrieval, citations, abstention, follow-ups, prompt injection, provider errors, input limits, and end-to-end flow have recorded test evidence.
- Similarity thresholds are calibrated from examples, not described as probabilities.
- Automated suite uses fake provider unless real-test flag is explicitly supplied.
- `plan.md` updated and phase committed.

### Phase 7 — Production model validation and final deployment

**Status:** pending

Deliverables:
- Confirm production OpenRouter model and strict test budget.
- Run a small explicitly authorized real-provider evaluation.
- Provision the compatible pinned model cache and RAG index under the Droplet's persistent data directory.
- Verify public frontend, backend readiness, representative answers, abstention, sources, and mobile layout.

Acceptance:
- Production works without personal OpenAI key.
- OpenRouter validation records model, case count, token usage when available, failures, and date without exposing secrets.
- Public URL is operational and documented.
- Known platform/control limitations remain explicit.
- `plan.md` updated and phase committed.

### Phase 8 — Submission preparation

**Status:** pending

Deliverables:
- Final README with verified install, run, ingestion, update, removal, rebuild, test, provider-switch, architecture, limitations, deployment URL, and ZIP instructions.
- Reproducible index/model preparation steps.
- Submission ZIP including `.git` while excluding secrets, dependencies, builds, virtual environments, model weights, and heavy caches.

Acceptance:
- Clean checkout instructions are reproducible.
- ZIP contents are inspected before delivery.
- Git history is present and secrets scan is clean.
- Final known issues are documented honestly.

## Verification Dataset Outline

Retrieval-positive categories:
- services and industries;
- booking a strategist call;
- client portal access;
- AI Maturity Index and assessment path;
- model selection;
- data security.

Abstention categories:
- unsupported pricing specifics;
- unverified case-study claims;
- requests to book a call or create a ticket;
- internal/private policy questions;
- unrelated topics;
- malicious instructions asking the bot to ignore evidence or reveal secrets.

Follow-up patterns:
- pronouns referring to a previously discussed service;
- “How do I get started?” after AI Maturity Index context;
- industry eligibility follow-up without repeating the industry.

Each case will identify expected source IDs or `must_abstain: true`. Retrieval metrics and generated-answer review remain separate.

## Risks and Limitations

- Official Cadre pages may be dynamic, sparse, changed, or inaccessible; content must be verified before inclusion.
- Portal, booking, contact, security, and pricing details may lack public authoritative evidence, forcing abstention.
- Small English embedding model may underperform on jargon, long pages, or non-English questions.
- FAISS and sentence-transformers increase backend build size and cold-start time; chosen hosting resources require validation.
- Persistent volume setup may incur cost and may complicate deploy-time index preparation.
- Prompt delimiting, source allowlisting, and citation validation reduce but do not eliminate prompt-injection or hallucination risk.
- In-memory rate limiting is not globally consistent, durable, or sufficient against distributed abuse.
- CORS does not prevent non-browser abuse.
- No authentication means portal questions can only return public instructions, never account-specific information.
- Session history is client-provided and untrusted; it can help interpretation but cannot establish facts.
- USD 5 OpenRouter budget constrains production evaluation and output length.
- Challenge recommends Claude Code/subagents, while user requires OpenCode-compatible sequential work without subagents; this may affect workflow evaluation.

## Pending Decisions Required Before Relevant Phases

1. **Production model:** confirm an OpenRouter model available to the challenge key after pricing/access review, before Phase 7.
2. **Generation secrets:** administrator credentials are configured on the Droplet; generation-provider keys are provided only through backend environment configuration in their later phase.

Phase 4 is authorized and in progress. Individual web sources become approved only through the authenticated administrator workflow and must remain within configured Cadre AI domains. Remaining decisions can wait until their listed phases.
