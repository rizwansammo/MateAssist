# MateAssist

Multi-tenant Agentic IT Helpdesk SaaS. Django REST Framework + PostgreSQL/pgvector
backend, React + Tailwind frontends, and a two-engine AI orchestration layer.

**Current state: Phase 0 (infrastructure provisioning).** No application code yet.

---

## The two-engine contract

The single most important rule in this codebase:

| Engine | Provider | Sees | Never sees |
|---|---|---|---|
| **Text & Reasoning** | DeepSeek | text chunks, image *descriptions*, conversation history | **images, ever** |
| **Vision & OCR** | Gemini | images | nothing else — it is called for image description only |

The handoff is always **image → text → reasoning**. Enforcement is structural, not
conventional: `TextEngine` has no parameter capable of carrying an image, and asserts
every content part is text at the one boundary all provider calls pass through.

## Documentation

| Document | Purpose |
|---|---|
| [docs/DECISIONS.md](docs/DECISIONS.md) | **The authoritative manifest.** 76 locked decisions + amendments. Anything not written there is not decided |
| [docs/PHASE-0.md](docs/PHASE-0.md) | Provisioning runbook, current blockers, exit criteria |

## Repository layout

```
backend/        Django 5.2 + DRF + Celery          (Phase 1)
frontend/
  portal/       End-User Portal   *.mateassist.io  (Phase 1)
  admin/        Super Admin Panel admin.mateassist.io
  packages/ui/  shared primitives, tailwind preset, HemiHead wordmark
infra/          docker-compose.yml + lifecycle scripts
docs/           decision manifest and phase runbooks
```

The two frontends stay separate bundles: the admin bundle is never served to a tenant
subdomain. That is an isolation guarantee route guards in a shared bundle cannot provide.

## Local setup

Requires **Python 3.12**, **Node 24**, and **Docker Desktop** (which requires WSL2 on
Windows Home — see [docs/PHASE-0.md](docs/PHASE-0.md) §2).

```powershell
# 1. Generate .env from the committed contract. Never overwrites without -Force.
powershell -ExecutionPolicy Bypass -File infra\scripts\generate-secrets.ps1

# 2. Check every prerequisite in one pass.
powershell -ExecutionPolicy Bypass -File infra\scripts\preflight.ps1

# 3. Start postgres + redis + minio, waiting for real health.
powershell -ExecutionPolicy Bypass -File infra\scripts\up.ps1

# 4. Phase 0 exit gate - proves pgvector actually works, not just that it exists.
powershell -ExecutionPolicy Bypass -File infra\scripts\verify.ps1
```

Host ports are **5433** (postgres) and **6380** (redis), not the defaults — native
services already hold 5432 and 6379 on the development machine. See amendment A-001.

`down.ps1` stops the stack and keeps data. `down.ps1 -DestroyData` deletes every volume
and demands you type `DESTROY`.

## Design system — non-negotiable

Zero border-radius everywhere, enforced twice over: a global
`* { border-radius: 0 !important }` base rule **and** an explicit `rounded-none` on every
primitive. A CI lint fails the build on any `rounded-{sm,md,lg,xl,full}` in a diff.

Palette `ink #0B1220` · `ink2 #101C2E` · `ink3 #0F1B2D` · `hairline #E2E8F0`, emerald
primary with cyan/amber accents. Typography IBM Plex Sans/Mono, with HemiHead for the
wordmark. All of it lives once, in `packages/ui`, and is inherited — neither app
re-declares a colour or a font, so divergence is structurally impossible.

## Security notes

`.env` is gitignored and holds `MATEASSIST_VAULT_KEY`, the AES-256-GCM KEK for every
stored provider API key. **Back it up.** Losing it means re-entering every key by hand.

Provider API keys are never stored in `.env` at runtime — they live encrypted in the
database vault, with no plaintext read path in any serializer. The two
`*_API_KEY_BOOTSTRAP` entries are dev-only, used solely by the Phase 1 model-ID
verification gate.
