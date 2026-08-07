# Phase 0 — Foundations & Infrastructure Provisioning

**Status: COMPLETE.** `verify.ps1` exits 0 — all five checks pass.
**Machine:** Windows 11 Home Single Language 10.0.26200
**Reference:** every `D-nnn` / `A-nnn` id refers to [DECISIONS.md](DECISIONS.md)

## Verified stack

```
PostgreSQL   17.10 (Debian 17.10-1.pgdg12+1)   127.0.0.1:5433
pgvector     0.8.6                             vector(384) + HNSW m=16 ef_construction=64 proven
Redis        7-alpine, appendonly=yes          127.0.0.1:6380
MinIO        bucket mateassist-documents       private (anonymous GET -> HTTP 403), versioned
Docker       engine 29.6.2, WSL2 backend
Python       3.12.10 via py -3.12
```

---

## 1. What is already done

| Item | State | Detail |
|---|---|---|
| Decision manifest | **done** | `docs/DECISIONS.md` — 76 locked decisions |
| `.gitignore` | **done** | written *before* any secret existed, so `.env` was never exposed to git |
| Env contract | **done** | `.env.example` — 52 keys, committed |
| Generated secrets | **done** | `.env` — gitignored, all `<generate>` placeholders filled |
| Python 3.12 | **done** | 3.12.10 at `%LOCALAPPDATA%\Programs\Python\Python312`, reachable as `py -3.12` |
| Compose stack | **written** | `infra/docker-compose.yml` — postgres 17 + pgvector, redis 7, minio, bucket bootstrap |
| Infra scripts | **written** | `preflight` · `up` · `down` · `verify` · `generate-secrets` |
| Docker Desktop | **BLOCKED** | not installed — see §2 |
| WSL2 | **BLOCKED** | not installed — see §2 |

Current preflight output:

```
  OK     Python 3.12                py -3.12
  BLOCK  Docker CLI                 not installed
  BLOCK  WSL2                       not installed - Docker Desktop cannot run without it
  OK     .env                       present, all secrets filled
  WARN   Provider keys              bootstrap keys blank - fine until Phase 4 (O-3)
  OK     port 5433                  postgres  (container 5432)
  OK     port 6380                  redis     (container 6379)
  OK     port 9000                  minio api
  OK     port 9001                  minio console
  WARN   port 5432                  native postgresql-x64-17 - expected; MateAssist avoids this port
  WARN   port 6379                  native redis-server - expected; MateAssist avoids this port
```

---

## 2. The two blockers — Administrator required

This is Windows 11 **Home**, so Docker Desktop has no Hyper-V backend option: it
**requires the WSL2 backend**. WSL2 is not installed, and installing it needs
elevation plus a reboot. Neither step can be automated from this session — an
elevated installer cannot be driven non-interactively, and a half-installed
Docker is worse than none.

Run these yourself, in an **Administrator** terminal:

```powershell
# 1. Install WSL2. Reboots are mandatory here, not optional.
wsl --install --no-distribution

# --- REBOOT ---

# 2. Install Docker Desktop.
winget install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements

# 3. Launch Docker Desktop once and wait for the whale icon to stop animating.
#    It must complete first-run setup before the CLI will answer.
```

Then, back in a normal (non-elevated) terminal at the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\preflight.ps1   # expect: clean
powershell -ExecutionPolicy Bypass -File infra\scripts\up.ps1          # start the stack
powershell -ExecutionPolicy Bypass -File infra\scripts\verify.ps1      # Phase 0 exit gate
```

`verify.ps1` exiting 0 is the definition of Phase 0 complete.

### Licensing note

Docker Desktop requires a paid subscription for commercial use in organisations
above Docker's size threshold. If Netswitch is over that line, use Option B
below instead — it needs no Docker at all.

---

## 3. Option B — the no-Docker, no-reboot fallback

Only if §2 is unacceptable. This trades production parity for immediacy, so it
is a documented fallback rather than the default.

| Service | Fallback | Cost of the compromise |
|---|---|---|
| PostgreSQL 17 + pgvector | **Managed Neon or Supabase** — pgvector is pre-enabled, ~5 minutes to provision | Network latency on every dev query; needs connectivity |
| Redis | **The native `redis-server` already running on 6379** | Not the pinned `redis:7-alpine`; behaviour may differ subtly |
| Object storage | **Django `FileSystemStorage`** under `backend/mediafiles/` | No S3 API surface, so presigned-URL logic goes untested until staging |

If you take Option B, only `.env` changes — `POSTGRES_*`/`DATABASE_URL` point at
the managed host, `REDIS_PORT` returns to `6379`, and a `STORAGE_BACKEND=filesystem`
key is added. **No application code branches on this.** The storage backend is
resolved once, from configuration, exactly as the provider model IDs are.

Say the word and I will produce the Option B `.env` overlay and a
`verify-optionb.ps1` that gates the same five checks against those endpoints.

---

## 4. Why the ports are non-default

Amendment **A-001**. This machine already runs two native services:

- `postgresql-x64-17` (Windows service, Automatic) listening on **5432**
- `redis-server` listening on **6379**

MateAssist therefore binds **5433** and **6380**. Nothing was stopped or
reconfigured — other projects on this machine keep working, and the native
PostgreSQL 17 was deliberately *not* reused because it has no pgvector
(`share\extension\vector*` is absent, and building it on Windows needs MSVC —
precisely the yak-shave D-011 exists to avoid).

Ports **8000** and **5173** were also occupied at survey time (a Python process
and a Vite dev server). Django keeps 8000 — that was a transient dev server, and
`.env` has `DJANGO_PORT` if it needs moving. The portal Vite app is assigned
**5175** and admin **5174**, since 5173 was taken.

---

## 5. What `verify.ps1` actually proves

Container-started is not the same as working, so the gate tests behaviour:

1. **PostgreSQL 17** — `SHOW server_version` matches `^17\.`
2. **pgvector present** — a row in `pg_available_extensions`
3. **pgvector functional** — in a *throwaway* database: `CREATE EXTENSION vector`,
   a `vector(384)` column at the configured `EMBEDDING_DIM`, an **HNSW index built
   with the exact D-057 parameters** (`m=16, ef_construction=64`), and a `<=>`
   cosine query returning the correct nearest neighbour. Then the scratch database
   is dropped.
   The app database is never touched — per **D-015** its extension is created by a
   Django migration, not by hand. This check answers "do vectors work?", not merely
   "is the file on disk?"
4. **Redis** — `PING` → `PONG`, and `appendonly=yes` confirmed so a queued
   ingestion chain survives a restart
5. **MinIO** — bucket exists, anonymous policy is `none` (private; access only via
   Django-signed URLs after a tenancy check), versioning enabled so a re-upload
   cannot silently destroy the prior runbook

---

## 6. Operational notes

**Back up `MATEASSIST_VAULT_KEY`.** It is the AES-256-GCM KEK for every provider
API key (D-071). Lose it and every stored key must be re-entered by hand.
`generate-secrets.ps1` refuses to overwrite an existing `.env` without `-Force`
for exactly this reason.

**PowerShell scripts are ASCII-only, deliberately.** Windows PowerShell 5.1
decodes BOM-less `.ps1` files with the system ANSI codepage, so a UTF-8 em-dash
inside a `-f` format string becomes mojibake and a hard parse error. ASCII source
removes the encoding dependency rather than papering over it with a BOM.

**`down.ps1 -DestroyData` requires typing `DESTROY`.** It deletes every tenant,
ticket, document, vector and uploaded file, with no backup taken.

---

## 7. Exit criteria

- [x] `docs/DECISIONS.md` locked
- [x] Python 3.12 installed and discoverable
- [x] `.env.example` contract committed; `.env` generated and gitignored
- [x] `infra/docker-compose.yml` + lifecycle scripts written
- [x] WSL2 installed (Ubuntu distro present)
- [x] Docker Desktop installed and running (engine 29.6.2)
- [x] `preflight.ps1` exits 0
- [x] **`verify.ps1` exits 0** ← the gate

**Phase 0 is closed. Phase 1 is cleared to start.**

## 8. Two harness bugs found by running it

Both were in my verification scripts, not the infrastructure — and both were
found only because the gate was actually executed rather than assumed.

**Native stderr under PowerShell 5.1 (amendment A-005).** `psql` emits a benign
`NOTICE: database "..." does not exist, skipping` on `DROP DATABASE IF EXISTS`.
PS 5.1 wraps every native-executable stderr line in an ErrorRecord, and with the
`$ErrorActionPreference = 'Stop'` inherited from `_common.ps1` that harmless
notice aborted the run. For native commands the authoritative success signal is
`$LASTEXITCODE`, never `$?`. Fixed by downgrading the preference in the scripts
that shell out — stderr is still captured for diagnostics — and by silencing
notices through `PGOPTIONS` rather than prepending a `SET` to the SQL, because
psql sends a multi-statement `-c` as one implicit transaction and
`CREATE DATABASE` cannot run inside a transaction block.

**A false-negative security assertion.** `mc anonymous set none` is reported back
by `mc anonymous get` as `private`, so a string match on `none` failed a bucket
that was correctly locked down. The fix was not to loosen the match: the check
now fails on the *dangerous* states (`public|download|upload|write`) and adds a
behavioural probe — an unauthenticated HTTP GET against the bucket that must be
refused, and is (HTTP 403). Asserting the property beats trusting a vendor's
wording.
