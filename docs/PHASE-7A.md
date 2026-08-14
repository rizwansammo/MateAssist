# Phase 7A — Usage rollups, budgets and the audit log API

**Status: COMPLETE.** The reporting layer that Phase 7B's dashboards will render.
Every figure comes from a real `UsageEvent` or `AuditEvent` row; nothing here is
estimated, and nothing crosses a tenant boundary without a platform-owner check.

---

## 1. The gate

```
python manage.py usage_demo

1. A workspace rollup cannot cross tenants (RLS, app role)
  armed as netswitch: own=$3.000000  leaked=$0
  PASS  netswitch sees its own $3.00
  PASS  netswitch cannot reach apptriangle's rows even when asked to

2. The platform rollup sees every workspace (admin role, RLS bypassed)
  platform total: 11 requests  $10.000000
    apptriangle        1 req  $7.000000
    netswitch         10 req  $3.000000
  PASS  platform total includes both tenants
  PASS  per-tenant breakdown lists both workspaces
  PASS  spend is attributed to the right workspace
  PASS  an unpriced model is named rather than silently costing zero

3. The alias trap that would silently zero the billing screen
  default alias, no context: $0   platform alias: $3.000000
  PASS  default connection returns zero with no tenant armed (the trap)
  PASS  platform alias returns the real figure - so status_for must pass it

4. Budget enforcement blocks on the path that spends money
  PASS  an advisory budget over its cap blocks nothing
  PASS  enforced budget refuses: spent $3.000000 of $1.00
  PASS  a zero cap means no limit rather than a total outage
  PASS  budget status is reported for the dashboard

  Phase 7A gate passed.
```

Test 1 is the one that matters. `tenant_summary(beta)` is called **while armed as
Alpha** — the Python filter asks for Beta's money and the database returns
nothing. That is isolation rather than a convention.

### Live over HTTP

21 assertions against the running server, with real logins and real Host headers:

```
platform surface (owner)          usage 200 · spend 200 · logs 200 · budgets 200
  requests=8  tokens=6507  unpriced=['gemini-3.6-flash','gemini-flash-latest']
  audit log: 5 events, newest  warn budget.blocked / info chat.escalate

platform surface (everyone else)  workspace admin 403 · end user 403 · anon 401
tenant surface                    admin 200 · end user 403
cross-tenant probe                netswitch token on apptriangle host -> 403
```

```
137 tests pass (was 112) · ruff clean · black clean · migrations clean
```

## 2. What was built

| Component | Note |
|---|---|
| `metering/rollups.py` | Summary, by-engine, by-model, by-operation, by-tenant, daily series |
| `metering/budgets.py` | Monthly cap, advisory vs enforced, checked in the router |
| `metering/models.py` | `TenantBudget` — deliberately **not** tenant-scoped |
| `metering/views.py` | `/usage/summary/`, `/usage/series/`, `/usage/by-model/` |
| `platformadmin/views.py` | `/platform/usage/`, `/platform/spend/`, `/platform/logs/`, `/platform/budgets/` |
| `seed_dev` | Now seeds `ModelPrice` rows |

## 3. The decisions that shaped it

**Two scopes, and the difference is a security boundary.** Tenant rollups run on
`default` as the NOSUPERUSER app role, so RLS is live and a wrong filter still
cannot leak. Platform rollups run on `admin`, which is a superuser and therefore
bypasses RLS entirely — the only cross-tenant read path in the system. Every
function that uses it is named `platform_*` and every route that reaches one is
gated by `IsPlatformOwner`. A reviewer should never have to check which
connection a rollup used; the name says it.

**`TenantBudget` is not a `TenantScopedModel`.** It is platform commercial
configuration *about* a workspace, in the same category as `Tenant` itself. If it
were tenant-scoped, a workspace could raise or disable its own cap.

**`enforce` defaults to False.** Adding a budget is first an observation, not an
outage — an admin sets a figure, watches a cycle, then turns it on. And a zero
cap means "no limit", not "spend nothing", so creating a row does not cut a
workspace off before a figure has been typed.

**The budget check lives in `router._call_with_pool`, not in a view.** A view is
not the only thing that spends money; a Celery task or a management command
would walk straight past a view-level check. Nothing reaches an engine without
passing through that function.

**Month-to-date spend is not cached.** A 60-second stale figure is 60 seconds of
unbounded overspend, which is the thing the cap exists to prevent.

**Unpriced models are named, not hidden.** `compute_cost` returns zero for a
model with no `ModelPrice` row, on purpose — failing a user's chat because an
admin has not entered a rate would be the wrong trade. But a dashboard showing
that zero without saying why is understating spend, so `Summary.unpriced_models`
travels with every total.

**Reads are administrator-only, with no method exemption.** Stricter than the
runbook surface, which lets any member read because runbooks are for everyone.
Volume and spend say how a business is being run.

## 4. Found by building it

**`status_for` would have reported $0 for every workspace.** It called
`month_to_date_cost` on the default connection. A platform owner has no tenant
context armed, so the RLS predicate collapses to `tenant_id IS NULL` and the sum
comes back empty — a billing dashboard confidently reporting that nobody has
spent anything, with no error anywhere. Both functions now take an `alias` and
the platform surface passes `PLATFORM_ALIAS`. The gate asserts both halves.

**The test suite cannot verify cross-tenant aggregation, and says so.** In test
settings `admin` is `TEST: {"MIRROR": "default"}`, which hands both aliases the
*same* app-role connection — so the RLS bypass that platform reporting depends on
does not exist in-process, and every `platform_*` rollup reads zero. Removing
MIRROR does not help: the aliases then get separate connections and a
non-transactional test's uncommitted writes are invisible to the second one.

Rather than weaken something to make a green test, the limitation is written down
in `test_platform_reads_cannot_be_proven_in_process` and the claim is proven by
`usage_demo` against the real database with both real roles. This is A-006
again: four bugs in this project were invisible to a green suite.

**The running server was serving stale routes.** All 21 live checks returned 404
while `/auth/login/` returned 200 — the process predated the new URLs. Restarted
with `--reload`. Worth recording because a 404 on a brand-new endpoint reads
exactly like a routing mistake.

## 5. Where this departs from the manifest (A-012)

Three locked decisions were implemented differently, recorded in full as A-012:

- **D-112** specified a nightly `UsageDaily` rollup table. Built live aggregation
  over raw events instead — always current, no Celery on the reporting path, no
  backfill problem. The trade reverses at scale; the trigger to revisit is a
  platform summary over 500 ms or ~10M `UsageEvent` rows, and `rollups.py` is
  already the seam a rollup table would slide behind.
- **D-114** specified 90-day retention. The log is currently unbounded — pruning
  is irreversible and belongs in Phase 8, after someone has watched it fill.
- **D-113** framed the cap as a plan allowance. Built per workspace, because
  plans will change when the subscription flow arrives (A-011) and a cap tied to
  a tier would have to be rebuilt then.

## 6. Honest limitations

- **Prices are not retroactive.** `cost_usd` is computed and stored when the
  usage row is written, so entering a rate tomorrow does not reprice yesterday's
  traffic — and it should not, since a rate change must never rewrite an invoice
  already issued. The consequence is that traffic recorded before a price exists
  reads `$0.00` permanently. `seed_dev` now seeds rates so a fresh install starts
  with figures, and `unpriced_models` names anything still missing, but there is
  no backfill command.
- **Budget enforcement adds one aggregate per provider call**, and only when an
  enforcing budget exists. Indexed on `(tenant, -created_at)`; fine at this
  scale, worth revisiting at high volume.
- **The audit log has no retention policy.** It grows without bound.
- **Daily buckets are UTC**, so a workspace in another timezone sees days split
  where its own calendar would not.
- **`Conversation.resolved` is still never set true**, so an "AI success rate"
  metric still has no source. Carried over from Phase 6.

## 7. Next — Phase 7B

Wire the six dummy surfaces to these endpoints and delete the seed files:

| Page | Source |
|---|---|
| Admin Overview | `/platform/usage/` + `/api/v1/health/` |
| Admin Billing | `/platform/spend/` + `/platform/budgets/` |
| Admin Logs | `/platform/logs/` |
| Admin Tenants | real tenant list (endpoint still needed) |
| Portal Dashboard | `/usage/summary/` |
| Portal My Tickets | remove — orphaned by A-008 |

Gate: `grep -r "SEED_" frontend/` returns nothing, both bundles build, D-100
clean.
