# MateAssist — Decision Manifest

**Status:** LOCKED for Phase 0 → Phase 1 handoff
**Date locked:** 2026-08-05
**Supersedes:** the tri-provider (Gemini/Groq/OpenAI) architecture implied by the reference prototypes

This is the authoritative record of every binding technical decision. Anything not written
here is not decided. Changing a `LOCKED` row requires an explicit amendment at the bottom of
this file, with a date and a stated migration cost — not a silent edit.

Decision IDs (`D-nnn`) are referenced from commit messages, ADRs and code comments.

---

## 1. Runtime & Toolchain

| ID | Decision | Value | Rationale |
|---|---|---|---|
| D-001 | Python | **3.12.x** (pinned; `.python-version` + `pyproject.toml` `requires-python = ">=3.12,<3.13"`) | Maximum wheel availability across `torch` / `sentence-transformers` / `PyMuPDF` / `psycopg[c]`. The machine's installed 3.14.6 is **not** used — ML and vector wheels are unreliable there on Windows. |
| D-002 | Web framework | **Django 5.2 LTS** + **Django REST Framework** | LTS support window; 5.2 officially supports Python 3.10–3.13, so D-001 is inside the supported matrix. |
| D-003 | Server model | **ASGI** via **Uvicorn** | Server-Sent Events for chat token streaming (D-041) require a non-blocking server. WSGI is disqualified. |
| D-004 | Task queue | **Celery 5.x** + Redis broker; `celery beat` for rollups | Ingestion is long-running and fan-out shaped (per-image Gemini calls). |
| D-005 | DB driver | **psycopg 3** | Required for modern Django; better `SET LOCAL` / server-side cursor handling for RLS (D-020). |
| D-006 | Node | **24.18.1** (machine default, accepted) | Already installed; Vite 5 and React 18 are compatible. |
| D-007 | Package managers | Backend: `pip` + `pyproject.toml` + lockfile. Frontend: **npm workspaces** | No new tooling to learn; workspaces are needed for `packages/ui` (D-050). |

---

## 2. Infrastructure — Local Development

| ID | Decision | Value |
|---|---|---|
| D-010 | Orchestration | **`infra/docker-compose.yml`** — single unified environment |
| D-011 | Database | **`pgvector/pgvector:pg17`** → PostgreSQL 17 with `pgvector` pre-built. Port `5432` |
| D-012 | Cache / broker | **`redis:7-alpine`**. Port `6379` |
| D-013 | Object storage | **`minio/minio`** — S3 API emulation. API `9000`, console `9001`. Bucket `mateassist-documents` |
| D-014 | App processes in dev | Django + Celery worker run **on the host** (Python 3.12), services in Docker | Avoids Windows bind-mount I/O penalty and keeps `torch` model caching fast. Everything is containerised for production (D-090). |
| D-015 | Migrations | `django-migrations` only. `CREATE EXTENSION vector;` runs in an initial data migration, not by hand |

### Practical gotchas recorded now, not discovered later

- **Port 6379 conflict.** A native Redis (`taizod1024.redis-windows-fork`) is installed on this
  machine. It must be stopped before `docker compose up`, or D-012 remaps to `6380`. The compose
  file is the source of truth; the native install is abandoned.
- **Subdomain dev.** Tenant resolution is host-based (D-021). See amendment **A-007** — the
  original claim here (that `*.localhost` resolves without configuration) is only true inside
  Chromium and Firefox, not for the OS resolver, and the strategy is settled in Phase 2.
- **Dev ports.** Django `8000` · portal `5173` · admin `5174`.

---

## 3. Multi-Tenancy & Isolation

| ID | Decision | Value |
|---|---|---|
| D-020 | Tenancy model | **Shared schema + `tenant_id` FK + PostgreSQL Row-Level Security.** *Not* `django-tenants` |
| D-021 | Tenant resolution | `Host` header → subdomain → `Tenant`. `SubdomainMiddleware` sets `SET LOCAL app.tenant_id` inside the request transaction |
| D-022 | Defence in depth | `TenantScopedManager` on every tenant-owned model, **in addition to** RLS. The ORM layer is convenience; RLS is the guarantee |
| D-023 | Celery isolation | Every task takes `tenant_id` as its first argument and opens with the same `SET LOCAL`. A task that cannot establish tenant context **fails closed** |
| D-024 | Roles | `PLATFORM_OWNER` · `TENANT_ADMIN` · `AGENT` · `END_USER` (on `Membership`, not `User`) |
| D-025 | Phase 2 exit gate | A test that bypasses `TenantScopedManager` with raw SQL and is **still** denied cross-tenant rows by RLS. **No phase proceeds until this passes** |

**Why RLS and not schema-per-tenant:** isolation is enforced at the storage layer, so an ORM
mistake, a raw query, or a Celery task that forgets to filter still cannot leak. Schema-per-tenant
would also fragment the pgvector index across schemas and multiply migration cost by tenant count.

**Known risk (tracked, not resolved):** `SET LOCAL` is connection-scoped. If PgBouncer is
introduced in transaction-pooling mode, the tenant variable must be set inside every transaction
or isolation breaks silently. Mitigation: the setting is always issued inside an explicit
`atomic()` block, and a regression test asserts denial under a pooled connection.

---

## 4. Authentication

| ID | Decision | Value |
|---|---|---|
| D-030 | Scheme | **`djangorestframework-simplejwt`**. Replaces the prototype's simulated state jump entirely |
| D-031 | Access token | 15 min TTL, held **in memory only** (never `localStorage`) |
| D-032 | Refresh token | 7 day TTL in an **httpOnly · Secure · SameSite=Lax** cookie, scoped to the API path. Rotation on use + blacklist |
| D-033 | User identity | Custom `User` model, **email as username**. No separate username field |
| D-034 | Login scope | Credentials are validated against the tenant resolved from the subdomain. The same email in two tenants is two distinct memberships |
| D-035 | Suspended tenant | Blocks sign-in **and** pauses AI routing immediately; existing sessions revoked |
| D-036 | Entra ID / SSO | **OUT OF SCOPE for v1.** The prototype's "Continue with Microsoft Entra ID" button is removed, not stubbed. A disabled button that looks real is worse than no button |

---

## 5. AI Engine Contract — the load-bearing decision

| ID | Decision | Value |
|---|---|---|
| D-040 | **Text & Reasoning Engine** | **DeepSeek.** Intent classification, RAG answering, ticket drafting, tool calling. **Receives text only — always** |
| D-041 | **Vision & OCR Engine** | **Gemini.** Image description and OCR **only**. Receives images, returns text, and is called nowhere else |
| D-042 | Handoff direction | Always **image → text → reasoning**. Never image → reasoning |
| D-043 | Enforcement point | The guard lives at the **client boundary** (`apps/ai/engines/text_deepseek.py`), the single chokepoint every text call passes through. `TextEngine` asserts every content part is `type="text"` and raises on bytes / `image_url` / `inline_data`. There is no parameter on `TextEngine` capable of carrying an image |
| D-044 | Providers removed | **Groq and OpenAI are deleted entirely** — cards, toggles, health rows, routing policy, log fixtures. No fallback provider in v1 |
| D-045 | Routing model | **Deterministic, not policy-driven.** With two engines holding fixed, non-overlapping roles there is nothing to route. The prototype's "Orchestration policy" toggles for Groq routing and OpenAI fallback are removed; the "Effective routing" panel becomes a read-only **Engine Assignment** display of the fixed D-040/D-041 contract |

### Pinned model IDs

| Role | Model ID | Notes |
|---|---|---|
| Primary RAG answering + tool calling | **`deepseek-chat`** | OpenAI-compatible API at `https://api.deepseek.com`; used via the `openai` SDK with a custom `base_url` |
| Escalation triage (optional, Phase 6+) | **`deepseek-reasoner`** | Reserved for hard diagnostic turns. Not on the default path — higher latency and token cost |
| Image description / OCR | ~~`gemini-2.5-flash`~~ → **`gemini-3.6-flash`** | **Amended by A-009** — the original pin is deprecated and 404s. Via the `google-genai` SDK |
| Embeddings | **`BAAI/bge-small-en-v1.5`** | Local, see D-060 |

> **VERIFICATION GATE (Phase 1, blocking).** These IDs are pinned from documentation current as
> of this manifest, not from a live probe. The first Phase 1 task is a connectivity script that
> calls each provider's model-listing endpoint and asserts every pinned ID resolves. If any has
> moved or been deprecated, **this file is amended before any engine code is written.** Model IDs
> are configuration (`ModelPrice` rows + env), never hardcoded constants — so a correction is a
> config change, not a refactor.

---

## 6. RAG Pipeline

| ID | Decision | Value |
|---|---|---|
| D-050 | Accepted upload formats | **`.pdf` · `.docx` · `.md`** (`.md` added this revision) |
| D-051 | PDF parsing | **PyMuPDF (`fitz`)** — text per page + `page.get_images()`. A page with no text layer is rasterised and treated as a single image |
| D-052 | DOCX parsing | **`python-docx`** for text; embedded images read from `word/media/*` in the zip container |
| D-053 | Markdown parsing | Plain text pass-through with heading structure retained. Referenced local images are resolved and sent through the Gemini path; remote/broken image links are logged and skipped, never fetched |
| D-054 | **Image position splicing** | Each Gemini description is re-inserted **at the image's original position** in the document's linear block stream *before* chunking, so a diagram is chunked in context with the procedure that references it — never as an orphaned blob. This is the pipeline's central design choice |
| D-055 | Chunking | Heading-aware, **~512 tokens, 15% overlap** |
| D-056 | Retrieval | **Hybrid** — pgvector cosine top-k ∥ PostgreSQL FTS (`tsvector`/GIN) top-k → **Reciprocal Rank Fusion, k=60** → top-6 to the prompt |
| D-057 | Vector index | **HNSW**, `vector_cosine_ops`, `m=16`, `ef_construction=64` |
| D-058 | Gemini cost control | Perceptual-hash dedupe across a document, minimum-dimension skip threshold, per-tenant ingestion budget cap. A 200-page screenshot-heavy runbook must not become 400 uncapped vision calls |

### D-060 — Embedding provider **(decided on your behalf — flagged for veto)**

**Locked: `BAAI/bge-small-en-v1.5`, 384-dim, run locally in the Celery worker via `sentence-transformers`.**

This was the one Phase 0 question your corrections did not answer, and it cannot be deferred:
the dimension is baked into the `vector(384)` column and the HNSW index, so switching later
means re-embedding **every chunk of every tenant**.

Chosen because it costs $0 per token in perpetuity, keeps tenant runbook text on infrastructure
you control, and is deterministic and offline-capable. Cost: ~130 MB of model weights in the
worker image and CPU time at ingestion only (never on the query path at scale).

Rejected: Gemini `text-embedding-004` (768-dim) — it would widen Gemini's role beyond the
images-only mandate in D-041 and meter every chunk.

Query-side convention: bge models require the prefix
`"Represent this sentence for searching relevant passages: "` on **queries only**, never on
stored passages. Asymmetry here silently degrades recall, so it is encoded in one function.

**To veto, say so before Phase 5 begins.** After the first tenant is indexed, this becomes a
migration with real cost.

---

## 7. Credential Vault

| ID | Decision | Value |
|---|---|---|
| D-070 | Storage | `ProviderKey(provider, label, ciphertext, last4, status, weight, daily_quota, requests_today, cooldown_until, added_at, last_used_at)` |
| D-071 | Encryption | **AES-256-GCM envelope encryption** under a KEK from env (`MATEASSIST_VAULT_KEY`). Never in source, never in the repo |
| D-072 | Write-only guarantee | The serializer has **no plaintext read field at all.** Write-only is not a flag to be misconfigured — it is the absence of a code path. Masked display uses `last4` only |
| D-073 | Pool routing | Round-robin, least-recently-used, `SELECT … FOR UPDATE SKIP LOCKED` for atomic acquisition. On `429`/quota → `cooldown_until` set, key skipped, traffic rebalanced |
| D-074 | Audit | Every create / rotate / revoke / purge writes an `AuditEvent` with actor and IP. Keys never appear in logs — enforced by a log-scrubber test |
| D-075 | UI masking | Secret inputs are `type="password"` with an explicit Show/Hide toggle, `autoComplete="off"`, `spellCheck={false}` |

---

## 8. Scope Subtractions — dropped, not deferred

Each item below is **removed from the codebase and the data model.** Nothing here becomes a
disabled control, a stub endpoint, or a "coming soon" state.

| ID | Dropped | Replacement |
|---|---|---|
| D-080 | **Chat "Conversation context" panel** — Device / OS / Location / Entra status (`MateAssistPortal.jsx:940-955`) | Nothing. Panel deleted |
| D-081 | **All MDM / Entra / client-device integration** | Out of scope entirely. Not a phase, not a backlog item |
| D-082 | **Article "read time"** and **"views this month"** | Real document metadata: file type, size, page count, chunk count, uploader, indexed-at |
| D-083 | **Article tag badges** (Popular / Updated / Policy / Runbook / Required) | Real `Document.status`: `INDEXED` · `INDEXING` · `FAILED` |
| D-084 | KB list header **"Most read this month"** | **"Recently updated"**, ordered by real `updated_at` |
| D-085 | **Groq** and **OpenAI** provider cards, toggles, health rows, log fixtures | Nothing. Two engines only (D-044) |
| D-086 | Policy toggles `groqRouting`, `openaiFallback` | Removed. `tenantCaps` **survives** as real budget enforcement (D-101) |
| D-087 | **ITSM connector** health row and webhook log fixtures | No external ITSM integration in v1. MateAssist *is* the helpdesk |
| D-088 | Hardcoded `AVATARS` map keyed by tenant name (`SuperAdminPanel.jsx:28-35`) | Deterministic colour derived from `tenant.slug` hash |
| D-089 | Sidebar **"Last incident 14 days ago"** | Derived from the real health aggregate. No incident model in v1 — if there is nothing to report, the line is absent |

### Retained on purpose — do not mistake these for dead metrics

- **The chat right-hand sidebar survives.** Only its first block is deleted. `Referenced articles`
  becomes **real RAG citations**; `Was this helpful?` becomes **real `MessageFeedback`**.
  (`MateAssistPortal.jsx:958-996`)
- **The login page's marketing panel** (`76% self-served · 41m · 24/7`) stays as **static brand
  copy**, explicitly not a metric. It renders pre-authentication, where no tenant context exists,
  so it is structurally incapable of being live. Recorded so it is never mistaken for a data bug.
- **"Margin guard"** panel is real — it is the platform budget cap (D-101).
- **Status Centre** rows are rebuilt against real dependencies: DeepSeek engine · Gemini engine ·
  PostgreSQL/pgvector · Redis/Celery queue · Object storage.

---

## 9. Net-New UI (not present in the prototypes)

| ID | Feature | Owner role |
|---|---|---|
| D-090 | **Runbook upload** — `.pdf`/`.docx`/`.md`, drag-drop, per-file progress, live indexing status, retry on failure, re-index | `TENANT_ADMIN` |
| D-091 | **Chat composer attachments** — clipboard **paste-screenshot**, drag-and-drop, file picker, thumbnail preview with remove-before-send, upload progress | `END_USER` |
| D-092 | **AI Configuration restructure** — two dedicated sections, exactly as specified: **"Text & Reasoning Engine"** (DeepSeek key management) and **"Vision & OCR Engine"** (Gemini key management). Each with its own pool table, add/rotate/revoke, and test-connection | `PLATFORM_OWNER` |
| D-093 | **Real login** — JWT, error states, per-tenant validation, session expiry (D-030→D-036) | all |

---

## 10. Design System — NON-NEGOTIABLE

| ID | Decision |
|---|---|
| D-100 | **Zero border-radius, globally and explicitly.** `* { border-radius: 0 !important }` in `packages/ui` base CSS is retained **and** every primitive, button, input, modal, card and view container carries an explicit `rounded-none`. Belt and braces: the global rule is the guarantee, the utility class is the intent. A CI lint rule fails the build on any `rounded-{sm,md,lg,xl,full}` or non-zero `border-radius` in the diff |
| D-101 | **Palette preserved byte-for-byte** from the prototypes: `ink #0B1220` · `ink2 #101C2E` · `ink3 #0F1B2D` · `hairline #E2E8F0`, with emerald primary and cyan/amber accents |
| D-102 | **Typography preserved:** `IBM Plex Sans` / `IBM Plex Mono` (body/mono), **`HemiHead-Bold.otf`** for the wordmark via the `font-wordmark` utility. The font file moves to `packages/ui/fonts/` unmodified |
| D-103 | `toastIn` keyframe and the toast component are preserved as-is |
| D-104 | **Single source of truth:** the Tailwind preset and `@font-face` live in `packages/ui` and are *inherited* by both apps. Neither app re-declares a colour or a font. Divergence becomes structurally impossible |

---

## 11. Metering, Billing & Audit

| ID | Decision | Value |
|---|---|---|
| D-110 | Usage events | Every provider call writes `UsageEvent(tenant, user, provider, model, operation, prompt_tokens, completion_tokens, image_count, cost_usd, latency_ms, request_id)`. **No provider call without a meter reading** |
| D-111 | Pricing | `ModelPrice(provider, model, input_per_1m, output_per_1m, per_image)` — **in the database, editable in admin.** Never hardcoded |
| D-112 | Rollups | `celery beat` nightly → `UsageDaily`. Dashboards read rollups, never raw events |
| D-113 | Budget enforcement | Soft warning at 80% of plan allowance; hard stop at 100% when `tenantCaps` is enabled. Platform-wide cap configurable, not a literal |
| D-114 | Audit log | `AuditEvent(actor, tenant, level, action, target, metadata, ip)` with levels `info · warn · error · auth`. Powers the System Logs live tail. **Metadata only — tenant payloads redacted.** 90-day retention |
| D-115 | Operational logging scope | Confined to real operational facts: ticket state transitions, RAG retrieval and usage events, vault operations, ingestion outcomes, auth events. No engagement or vanity metrics anywhere in the schema |

---

## 12. Escalation — SMTP handoff (supersedes the internal helpdesk domain)

**Superseded by amendment A-008 (2026-08-07).** MateAssist does not store tickets.
When the agent cannot solve an issue it hands off by email to the customer's existing
helpdesk. D-120–D-123 below are retained only as the record of what was replaced.

| ID | Decision | Value |
|---|---|---|
| D-124 | Escalation transport | **SMTP / SendGrid.** No `Ticket`, `Comment` or status state machine in this system |
| D-125 | Tool name | The agent tool is **`escalate_via_email`**, not `create_ticket` |
| D-126 | Human-in-the-loop | Unchanged in spirit: the tool call **renders a button; the user's click sends.** The model never emails anyone on its own |
| D-127 | Payload | Full transcript + retrieved citations (with document titles) + Gemini image descriptions, as a readable email body |
| D-128 | Destination | `Tenant.support_email`, set per workspace, falling back to a platform default. A tenant's escalations must never reach another tenant's helpdesk |
| D-129 | Record kept | An `AuditEvent` per escalation (recipient, message-id, outcome). The transcript is **not** retained beyond the conversation |

### Retired (paused indefinitely)

| ID | Was |
|---|---|
| ~~D-120~~ | Per-tenant ticket numbering by database sequence |
| ~~D-121~~ | `Open → Pending → Resolved` state machine |
| ~~D-122~~ | `create_ticket` tool writing to a local table |
| ~~D-123~~ | Escalation payload attached to a ticket row |

---

## 13. Security Posture

| ID | Decision |
|---|---|
| D-130 | **Ingested content is untrusted input.** Runbook text and Gemini image descriptions are wrapped in delimiters with an explicit instruction never to obey embedded directives. **Retrieved text can never authorise a tool call** — only the authenticated user can |
| D-131 | Upload safety: MIME sniffing (not extension trust), size caps, ClamAV scan, path-traversal-proof storage keys |
| D-132 | DRF throttles per user / tenant / IP, tightest on chat and upload |
| D-133 | Full RBAC matrix test: every endpoint × every role, including deliberate cross-tenant attempts |
| D-134 | Backups include a **restore rehearsal**. An untested backup is not a backup |

---

## 14. Deployment Target

| ID | Decision |
|---|---|
| D-140 | Fully containerised: backend · worker · beat · two static frontend bundles |
| D-141 | Caddy/Nginx TLS terminator → Uvicorn workers → managed PostgreSQL 17 + pgvector → Redis → Celery → S3-compatible storage |
| D-142 | **Wildcard TLS for `*.mateassist.io`** — mandated by subdomain tenancy (D-021). Requires DNS-01 challenge and therefore **registrar API access** |
| D-143 | SSE through the proxy requires `X-Accel-Buffering: no`. Verified in staging, never assumed |
| D-144 | Zero-downtime migrations: additive first → deploy → backfill → drop in a later release |
| D-145 | Two React bundles stay separate. **The admin bundle is never served to a tenant subdomain** — an isolation guarantee route guards in a shared bundle cannot provide |

---

## Open Items

| # | Item | Blocking | Owner |
|---|---|---|---|
| O-1 | **D-060 embedding provider** decided on your behalf. One-line veto accepted any time before Phase 5 | No (blocks Phase 5) | You |
| O-2 | **Registrar API access** for the D-142 DNS-01 wildcard challenge | No (blocks Phase 9) | You |
| O-3 | **DeepSeek + Gemini API keys** for the Phase 1 verification gate (§5) and Phase 4 live testing | No (blocks Phase 4) | You |
| O-4 | Production hosting target — cloud provider and region | No (blocks Phase 9) | You |

---

## Amendments

Append only. Date, affected decision IDs, and the migration cost of the change.

---

### A-001 — Host ports remapped to 5433 / 6380
**Date:** 2026-08-05 · **Amends:** D-011, D-012 · **Migration cost:** none (dev-only)

Provisioning survey found two native Windows services already holding the default ports:

- `postgresql-x64-17` (Windows service, startup Automatic) on **5432**
- `redis-server` (winget `taizod1024.redis-windows-fork`) on **6379**

MateAssist's containers now bind **5433 → 5432** and **6380 → 6379**. Nothing on the
machine was stopped or reconfigured, so other projects on this Desktop keep working.
Container-internal ports are unchanged, so production (D-141) is unaffected — this is
purely a host-side mapping.

`.env` is the single source of truth for both (`POSTGRES_PORT`, `REDIS_PORT`), and
`preflight.ps1` reports the native listeners as expected `WARN`s rather than errors so
they are never mistaken for a misconfiguration.

**The native PostgreSQL 17 was deliberately not reused.** It is the right version, but
`share\extension\vector*` and `lib\vector*` are both absent — pgvector is not installed,
and building it against a native Windows PostgreSQL requires an MSVC toolchain. That is
exactly the yak-shave D-011 was written to avoid. The container image ships pgvector
prebuilt.

Also occupied at survey time: **8000** (a stray Python process) and **5173** (a Vite dev
server, likely a reference prototype). Django keeps 8000 with `DJANGO_PORT` available if
it must move. The Vite apps take **5175** (portal) and **5174** (admin).

---

### A-002 — Docker Desktop requires WSL2 on this machine
**Date:** 2026-08-05 · **Amends:** D-010 · **Migration cost:** none · **Status:** open blocker

The host is **Windows 11 Home Single Language**, which has no Hyper-V backend option for
Docker Desktop — the **WSL2 backend is mandatory**. WSL2 is not installed
(`wsl --status` fails; `HypervisorPresent` is true, so virtualisation itself is fine).

Consequence: D-010 carries a prerequisite that cannot be satisfied from a non-interactive
session. `wsl --install` and the Docker Desktop installer both need Administrator
elevation, and WSL2 needs a reboot. Remediation is documented in
[PHASE-0.md](PHASE-0.md) §2 and owned by the user.

A no-Docker fallback (managed Postgres + the already-installed native Redis + Django
`FileSystemStorage`) is documented in [PHASE-0.md](PHASE-0.md) §3. It is a **fallback,
not a co-equal option** — it costs production parity and leaves presigned-URL logic
untested until staging. If adopted, only `.env` changes; no application code branches on
it, because the storage backend resolves from configuration exactly as provider model IDs
do (D-045 note).

A licensing consideration is recorded alongside it: Docker Desktop requires a paid
subscription for commercial use in organisations above Docker's size threshold.

---

### A-003 — Python pinned to 3.12.10
**Date:** 2026-08-05 · **Amends:** D-001 · **Migration cost:** none

Installed via `winget install --id Python.Python.3.12 --scope user` (no elevation
required). Resolves to:

```
py -3.12  ->  C:\Users\Rizwan\AppData\Local\Programs\Python\Python312\python.exe
              3.12.10 (tags/v3.12.10:0cc8128, Apr 8 2025) [MSC v.1943 64 bit (AMD64)]
```

The pre-existing 3.14.6 remains the machine default (`py` with no argument) and is
untouched. All MateAssist tooling must invoke `py -3.12` explicitly, or use the project
virtualenv created from it in Phase 1. `.python-version` records the pin.

---

### A-004 — Infra scripts are ASCII-only
**Date:** 2026-08-05 · **Amends:** none (new constraint) · **Migration cost:** none

Windows PowerShell 5.1 — the shell on this machine — decodes BOM-less `.ps1` files using
the system ANSI codepage. A UTF-8 em-dash inside a `-f` format string therefore becomes
mojibake and a **hard parse error**, which is how the first `preflight.ps1` run failed.

Constraint: **every `.ps1` under `infra/` stays pure ASCII.** Chosen over adding a UTF-8
BOM because it removes the encoding dependency instead of relying on correct BOM
detection at every layer that touches the file (git, editors, CI checkout).

---

### A-005 — Native-command stderr must never be treated as failure
**Date:** 2026-08-05 · **Amends:** none (new constraint) · **Migration cost:** none

Windows PowerShell 5.1 wraps **every** stderr line from a native executable in an
ErrorRecord and sets `$?` to `$false` — even when the process exits 0. Under
`$ErrorActionPreference = 'Stop'`, a harmless `psql` NOTICE
(`database "..." does not exist, skipping` from `DROP DATABASE IF EXISTS`) therefore
aborted the entire Phase 0 gate.

Constraints, applying to every script that shells out (see A-007 for the tenancy-dev
correction that Phase 1 surfaced):

1. **`$LASTEXITCODE` is the only authoritative success signal for a native command.**
   Never `$?`, never the absence of stderr.
2. Scripts invoking native executables set `$ErrorActionPreference = 'Continue'` at
   script scope. stderr is still captured for diagnostics — it just stops being fatal.
3. Suppress expected notices at the source via environment (`PGOPTIONS=-c
   client_min_messages=warning`), **not** by prepending `SET` statements to the SQL:
   `psql -c` sends a multi-statement string as one implicit transaction, and
   `CREATE DATABASE` cannot run inside a transaction block.

This generalises beyond Phase 0 — it governs the Django `manage.py`, Celery and
`npm` wrappers written in later phases.

---

### A-006 — Security assertions test behaviour, not vendor wording
**Date:** 2026-08-05 · **Amends:** D-013 · **Migration cost:** none

The Phase 0 gate asserted bucket privacy by string-matching `mc anonymous get` for
`none`. Modern `mc` reports a bucket with no anonymous policy as `private`, so a
correctly locked-down bucket **failed** the check — a false negative that, had the
strings been reversed, would have been a false *positive* on a security property.

Corrected in two ways rather than by loosening the match:

1. The policy check now fails on the **dangerous** states
   (`public|download|upload|write`) and treats `none|private` as equivalent, so a
   future wording change cannot turn the check green by accident.
2. A **behavioural probe** was added: an unauthenticated HTTP GET against the bucket
   that must be refused (observed: HTTP 403).

Principle carried forward: where a decision asserts a security property, the test
exercises the property. D-025's cross-tenant RLS gate already follows this — it
bypasses the ORM and asserts the database still denies the read.

---

### A-007 — `*.localhost` does not resolve outside the browser
**Date:** 2026-08-07 · **Amends:** D-010 dev note, D-021 · **Migration cost:** none
**Status:** open decision, owned by Phase 2

The Phase 0 note claimed `netswitch.localhost` resolves to `127.0.0.1` without configuration.
Measured in Phase 1, that is **only half true**, and the half that fails is the one automated
tests depend on:

```
[Dns]::GetHostAddresses("netswitch.localhost")  ->  No such host is known
Invoke-WebRequest http://netswitch.localhost:5175/  ->  could not be resolved
```

Chromium and Firefox special-case `*.localhost` internally (RFC 6761), so a developer
clicking around a tenant subdomain works. **Every non-browser client fails**: the Windows OS
resolver has no wildcard entry, so PowerShell, curl, Python `requests`, Node `fetch` and any
integration test asserting tenant isolation over HTTP cannot reach it.

Compounding it, Vite's default `server.host: "localhost"` binds **`::1` only**, while browsers
map `*.localhost` to IPv4 `127.0.0.1` — so even in a browser the dev server would have been
unreachable on a tenant subdomain.

**Fixed now:** both Vite configs set `server.host: true`, binding all interfaces. This exposes
the dev server on the LAN; acceptable for a development machine, and it is never how
production serves (D-141).

**Left open for Phase 2**, because the tenancy middleware is what actually needs it:

| Option | Trade-off |
|---|---|
| Hosts-file entries per dev tenant | Works everywhere; needs Administrator and manual upkeep per tenant |
| A wildcard DNS service (`lvh.me`, `nip.io`) | No admin, resolves for OS and browser alike; requires internet and trusts a third-party resolver |
| `X-Tenant` header override in dev only | No DNS at all, but diverges from the production Host-header path — the riskiest, since the thing under test stops being the thing that ships |

Recorded rather than settled: picking one belongs with the middleware that consumes it, and
D-025's isolation gate is what will prove the choice works.

---

### A-008 — Internal ticketing replaced by an SMTP handoff
**Date:** 2026-08-07 · **Amends:** D-120–D-123 (retired), §12 · **Migration cost:** none — nothing was built

Phase 3 is **skipped**. MateAssist stores no tickets. When DeepSeek cannot resolve an issue,
the backend compiles the transcript, the retrieved citations and any Gemini image descriptions
and emails them to the workspace's existing helpdesk (D-124–D-129).

The build order is now **Phase 4 → 5 → 6**: vault and engine contracts, ingestion and vectors,
then agentic RAG chat. Ticketing may return as a final phase or never.

**What this removes:** `Ticket`, `TicketComment`, `TicketAttachment`, `TicketEvent`, `Queue`,
SLA clocks, the status state machine and per-tenant ticket numbering. None had been written, so
there is nothing to unwind.

**What it changes elsewhere — open, and flagged to the user:**

1. The portal's **My Tickets** page and the dashboard's ticket metrics (open count, average
   resolution, assigned engineer) now have no backend and never will. They are currently
   rendering `seed/tickets.js`. Leaving a fake ticket table in a shipped product contradicts the
   project's own premise, so they must be either removed or replaced with something real.
   Recommended: remove My Tickets, and replace the metric row with figures the AI layer actually
   produces — conversations, resolution rate, escalations sent, documents indexed.
2. The chat action button changes from *Create Ticket* to an email handoff, and the ticket
   confirmation card becomes an email-sent confirmation.
3. **Data egress posture changes.** A transcript leaving over SMTP is plaintext in transit to a
   third-party mail provider and is retained in the customer's mailbox indefinitely. That is a
   materially different privacy profile from a row in a tenant-isolated database, and it is worth
   a deliberate decision on redaction before Phase 6 wires it up.

**New configuration required (Phase 6):** `Tenant.support_email`, an SMTP/SendGrid credential
set, and `DEFAULT_FROM_EMAIL`. The provider credential belongs in the same encrypted vault as
the AI keys (D-070/D-071) rather than in `.env`, since it is a rotatable third-party secret.

---

### A-009 — The pinned Gemini model was already dead
**Date:** 2026-08-08 · **Amends:** §5 model pins · **Migration cost:** none — an `.env` change

The O-3 verification gate finally ran, and the pin failed on first contact.

`gemini-2.5-flash` — pinned since Phase 0 from documentation — returns:

```
404 NOT_FOUND: This model models/gemini-2.5-flash is no longer available to
new users. Please update your code to use a newer model.
```

`gemini-2.5-flash-lite` is dead the same way. **New pin: `gemini-3.6-flash`**, verified by a
real image call that correctly described a generated test image. `gemini-3.5-flash` and
`gemini-flash-latest` also work and are documented fallbacks.

**Three things this proved, none of which a unit test could have:**

1. **`models.list()` cannot be trusted.** `gemini-2.5-flash` is *listed* by the API and then
   404s when called. Any verification that only checks the catalogue is theatre — which is why
   `verify_providers` makes a real minimal call per engine.
2. **A per-call SDK client is a bug.** `genai.Client(...)` builds an httpx transport that closes
   when the object is collected, so a throwaway client can be shut down mid-request
   (*"the client has been closed"*). Both engines now cache the client on the instance.
3. **D-045 was right and is now proven.** Model ids being configuration rather than constants
   meant this deprecation cost one `.env` line, not a refactor.

**Operational findings for Phase 5:**

- **A 96×96 image costs ~1,100 input tokens.** Image tokens dominate ingestion: a 200-image
  runbook is ~220k tokens before any text. This is the number D-058's dedupe and
  minimum-size threshold exist to control, and it is larger than assumed.
- **The free tier exhausts quickly** — a handful of probe calls rate-limited
  `gemini-2.0-flash`. The Phase 4 key pool (round-robin, 429 cooldown, failover) is exactly the
  mitigation, but it needs **more than one key** to fail over to. Recommend 2–3 free keys before
  ingesting anything sizeable.
- **Google's API key format changed** to `AQ.…`; the older `AIzaSy…` assumption is stale and has
  been removed from the verification command's guidance.

**Standing rule:** re-run `manage.py verify_providers` whenever a model pin changes, and treat a
green result as perishable. This one was stale within months.
