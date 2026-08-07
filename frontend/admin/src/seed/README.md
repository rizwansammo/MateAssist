# Seed data — temporary, phase-scoped

Placeholder data kept only so the decomposed admin views render before their
backends exist. Isolated here so the remaining work stays greppable.

| File | Feeds | Deleted by |
|---|---|---|
| `platform.js` → `SEED_TENANTS` | Tenant Management, Overview counts | **Phase 2** — tenancy API |
| `engines.js` → `SEED_KEYS` | Key pool tables in AI Configuration | **Phase 4** — credential vault |
| `platform.js` → `SEED_USAGE`, `SEED_PROVIDER_SPEND` | Usage & Billing | **Phase 7** — metering rollups |
| `platform.js` → `SEED_LOGS`, `SEED_HEALTH` | System Logs, Status Centre | **Phase 7** — AuditEvent + health |

`engines.js` → `ENGINES` and `ENGINE_ASSIGNMENT` are **not** seed data. They
express the D-040/D-041 engine contract for the UI and survive Phase 4.

## Removed under the locked scope subtractions — do not reintroduce

- **Groq** and **OpenAI** provider cards, toggles, health rows and log lines (D-044, D-085)
- Orchestration policy toggles `groqRouting` and `openaiFallback` (D-086).
  `tenantCaps` survived as real budget enforcement and lives on the billing page.
- The prototype's **"Effective routing"** panel. With two engines in fixed,
  non-overlapping roles there is nothing to route, so it is now a read-only
  **Engine Assignment** statement of the contract (D-045).
- **ITSM connector** health row and webhook retry log lines (D-087) — MateAssist
  *is* the helpdesk; there is no external ITSM integration in v1.
- Hardcoded per-tenant avatar colour map (D-088) — now derived from the slug in
  `lib/avatar.js`.
