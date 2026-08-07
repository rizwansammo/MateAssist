# Phase 1 — Skeleton & Contracts

**Status: COMPLETE.** Exit gate green — `/api/v1/health` returns real dependency status,
reached from the frontend through the Vite proxy.

**Reference:** every `D-nnn` / `A-nnn` id refers to [DECISIONS.md](DECISIONS.md).

---

## 1. Exit gate

The Phase 1 criterion was "both apps render as the prototypes did, on real routes, with one
genuine API call proving the wire works." Measured, not asserted:

```
GET http://localhost:5175/api/v1/health/     (through the Vite dev proxy)
HTTP 200   overall: ok

  database         ok   PostgreSQL 17.10 (Debian 17.10-1.pgdg12+1)
  pgvector         ok   extension 0.8.6 installed
  redis            ok   PONG from Redis 7.4.10
  celery_broker    ok   broker connection established
  celery_workers   ok   1 worker(s): phase1@RootSurfer
```

Supporting checks, all run:

| Check | Result |
|---|---|
| `manage.py check` | 0 issues |
| `manage.py check --deploy --settings=config.settings.prod` | **0 issues** |
| `manage.py makemigrations --check` | No changes detected |
| `pytest` | **14 passed** |
| `npm run build` (both apps) | portal 212 KB, admin 218 KB, font emitted |
| `npm run lint:radius` | clean — and verified to fail on a planted `rounded-lg` |
| Celery round-trip | `ping.delay()` → `pong` through Redis to the worker |

---

## 2. Backend

```
backend/
  config/        settings/{base,dev,prod}.py, asgi.py, wsgi.py, celery.py, urls.py
  apps/
    core/        health checks, pgvector migration, tests      <- implemented
    accounts/    User model                                    <- implemented
    tenancy/ helpdesk/ ai/ knowledge/ chat/ metering/ audit/ platformadmin/
                                                               <- placeholders
```

**Django 5.2.17 LTS · DRF 3.17.2 · Celery 5.6.3 · psycopg 3.3.4**, on Python 3.12.10 in
`backend/.venv`.

### Two things pulled forward deliberately

**The `User` model (normally Phase 2).** Django freezes `AUTH_USER_MODEL` into the first
migration; swapping it afterwards means destroying the database. It had to exist before
`migrate` ran even once (D-033). Only the identity landed — membership, roles and JWT remain
Phase 2.

**The pgvector migration.** `core.0001_enable_pgvector` satisfies D-015: the extension is
created by a migration, never by hand. Phase 0's gate deliberately proved pgvector in a
throwaway database and left the app database untouched so this migration stayed the only path
that installs it.

### The health endpoint exercises dependencies rather than reporting config

Following the A-006 precedent. It runs a real query, a real `PING`, a real broker handshake.
Two design points worth knowing:

- **Required vs optional.** A missing Celery worker is normal in dev and during a rolling
  restart, so it is `required=False` and yields `degraded`/HTTP 200. Only a required failure
  returns 503. A false outage is its own incident.
- **The worker probe is cached (15s).** `control.ping` is a broadcast costing its timeout plus
  mailbox setup — **770 ms measured**. Uncached, a load-balancer poll every few seconds would
  make the health check the slowest thing in the system. Cached it is ~3 ms, and the whole
  endpoint answers in ~31 ms.

---

## 3. Frontend

```
frontend/
  packages/ui/   tailwind-preset.js, styles/base.css, fonts/HemiHead-Bold.otf,
                 components/{Wordmark,Pill,Metric,Switch,QuickAction,Toast}
  portal/        login, dashboard, chat, tickets, knowledge      (*.mateassist.io)
  admin/         overview, tenants, ai, billing, logs            (admin.mateassist.io)
  scripts/check-radius.mjs
```

Two separate bundles, npm workspaces. The admin bundle is never served to a tenant
subdomain (D-145).

### Decomposition

The two 1,242 and 1,268-line single-component prototypes became route-level pages under React
Router. `currentView` string state is gone: the browser back button, deep links and per-route
code splitting now work. The tenant log filter is a query parameter, so "View logs" produces a
shareable URL instead of hidden state.

### Design system — one source, inherited twice

`packages/ui` owns the preset, the base CSS and the font. Neither app re-declares a colour or a
font family (D-104). The palette and typography are byte-for-byte from the prototypes.

**D-100 is enforced two ways, on purpose.** The global
`* { border-radius: 0 !important }` is the guarantee — it cannot be forgotten on a new component
and it defeats radius baked into third-party CSS. The explicit `rounded-none` on every primitive
is the intent, visible at the call site. `scripts/check-radius.mjs` runs in CI and was **verified
against a planted violation**, not just observed to pass.

### Scope subtractions applied

| Removed | Decision |
|---|---|
| Device / OS / Location / Entra chat sidebar | D-080 |
| Article read-time and view counts | D-082 |
| Popular / Updated / Policy tag badges → real `Document.status` | D-083 |
| "Most read this month" → "Recently updated" | D-084 |
| Groq and OpenAI cards, toggles, health rows, log lines | D-044, D-085 |
| `groqRouting` / `openaiFallback` policy toggles | D-086 |
| "Effective routing" panel → read-only **Engine Assignment** | D-045 |
| ITSM connector health row and webhook logs | D-087 |
| Hardcoded tenant avatar colour map → derived from slug | D-088 |
| Hardcoded "Last incident 14 days ago" | D-089 |
| "Continue with Microsoft Entra ID" button | D-036 |

**Retained on purpose:** the chat right-hand sidebar survives minus its first block —
`Referenced articles` becomes real RAG citations and `Was this helpful?` becomes real
`MessageFeedback`. The login marketing panel stays as static brand copy; it renders
pre-authentication where no tenant context exists.

### AI Configuration, restructured (D-092)

Two dedicated sections exactly as specified: **Text & Reasoning Engine (DeepSeek)** and
**Vision & OCR Engine (Gemini)**, each with its own key pool, add/rotate/revoke, and a
password-masked secret input with show/hide (D-075).

Each section renders what its engine **receives** and **never receives**. The separation is the
product's central safety property, so an operator standing in the key vault should be able to
read it. Only the last four characters of any key exist client-side — the plaintext has no read
path (D-072).

---

## 4. Seed data is quarantined, not scattered

`portal/src/seed/` and `admin/src/seed/` hold every remaining placeholder, each with a README
naming the phase that deletes it. Dummy data spread through components is how a prototype
quietly ships; dummy data in one folder with a deletion owner is a to-do list.

| Seed | Deleted by |
|---|---|
| tickets | Phase 3 |
| tenants | Phase 2 |
| provider keys | Phase 4 |
| knowledge documents | Phase 5 |
| chat messages | Phase 6 |
| usage, logs, health | Phase 7 |

`engines.js → ENGINES` and `ENGINE_ASSIGNMENT` are **not** seed data — they express the
D-040/D-041 contract and survive Phase 4.

---

## 5. Deliberately absent

Things a reader might expect to find, left out for a reason:

- **No auth guard on any route.** Phase 2 adds `<RequireAuth>` once JWT issuance exists. A guard
  that checks nothing looks like security while providing none.
- **No token handling in `lib/api.js`.** The 401 → refresh → retry interceptor is Phase 2. The
  client already sends `credentials: "include"` so the httpOnly refresh cookie works the moment
  it is issued.
- **No chat attachment UI.** Paste-screenshot, drag-drop and preview (D-091) land in Phase 6
  alongside the Gemini describe path, so the UI ships with a backend that can test it.
- **No runbook upload UI.** D-090, Phase 5, same reasoning.

---

## 6. Found by running it

**A-007 — `*.localhost` does not resolve outside the browser.** The Phase 0 note claimed it did.
Measured: the Windows OS resolver returns *No such host is known*, so PowerShell, curl, Python
`requests` and any integration test asserting tenant isolation over HTTP cannot reach a tenant
subdomain. Only Chromium and Firefox special-case it internally.

Compounding it, Vite's default `server.host` binds **`::1` only** while browsers map
`*.localhost` to IPv4 `127.0.0.1` — so even in a browser the dev server was unreachable on a
subdomain. Both configs now set `host: true`. The DNS strategy itself is left open for Phase 2,
where the tenancy middleware that needs it lives.

**A bug in the D-100 lint.** The first version flagged the word "rounded" inside a prose comment
explaining the rule, and its zero-value lookahead backtracked past whitespace so
`border-radius: 0 !important` read as a violation. A linter that flags its own documentation gets
switched off, so it now strips comments and judges the captured CSS value in code.

---

## 7. Exit criteria

- [x] Django 5.2 LTS + DRF + ASGI + Celery skeleton
- [x] `AUTH_USER_MODEL` set before the first migration
- [x] pgvector enabled by migration (D-015)
- [x] `/api/v1/health` exercising DB, pgvector, Redis and the Celery broker
- [x] Backend tests green, including a behavioural pgvector probe
- [x] `packages/ui` extraction; neither app redeclares a colour or font
- [x] Both prototypes decomposed into route-level pages
- [x] Scope subtractions applied
- [x] AI Configuration restructured to the two-engine specification
- [x] D-100 lint in place and verified against a planted violation
- [x] Both bundles build
- [x] Frontend reaches the API through the proxy
- [ ] **Provider model-ID verification gate** — blocked on open item **O-3** (DeepSeek and
      Gemini API keys). Not on the Phase 1 critical path; it gates Phase 4.

## 8. Next — Phase 2

Tenancy and isolation. `Tenant`, `Membership` and the four roles; `SubdomainMiddleware`;
PostgreSQL RLS policies; JWT issuance with the httpOnly refresh cookie; real login replacing the
placeholder.

**The gate is D-025:** a test that bypasses the ORM with raw SQL and is *still* denied
cross-tenant rows by the database. Nothing downstream is worth building until that passes.
