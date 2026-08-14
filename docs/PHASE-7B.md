# Phase 7B — Dashboards on real data, and the end of the seed directories

**Status: COMPLETE.** Every screen in both apps now renders figures the backend
produced. `frontend/*/src/seed/` no longer exists.

---

## 1. The gate

```
seed directories        both deleted, no imports remain
D-100 radius lint       clean
frontend build          portal 225 kB · admin 236 kB · both green
backend                 152 tests pass (was 137) · ruff clean · black clean
                        migrations clean · usage_demo exit 0
live HTTP               every endpoint the rebuilt screens call, asserted field
                        by field, plus 7 access-control probes
```

The end-to-end proof that the numbers are real, not just present:

```
manage.py chat_demo --question "How do I reconnect the VPN?"
  tokens=598+146  latency=4399ms  model=gemini-flash-latest  METERED

GET /platform/usage/
  requests=9  cost=$0.000544
```

One real Gemini call, metered, priced from a `ModelPrice` row, aggregated across
tenants, and rendered on the Billing screen. That is the whole chain the
prototype faked with `SEED_USAGE`.

## 2. What changed

| Screen | Was | Now |
|---|---|---|
| Admin Overview | `SEED_HEALTH`, `SEED_USAGE` | `/platform/usage/` + real `/health/` |
| Admin Billing | `SEED_USAGE`, `SEED_PROVIDER_SPEND` | `/platform/spend/`, `/platform/budgets/` |
| Admin Logs | `SEED_LOGS` | `/platform/logs/`, filtered server-side |
| Admin Tenants | `SEED_TENANTS` | `/platform/tenants/` with annotated counts |
| Portal Dashboard | `seed/tickets.js` | real conversations + runbook count |
| Portal My Tickets | `seed/tickets.js` | **deleted** (A-008) |

New shared pieces: `lib/platform.js` (client), `lib/useResource.js`
(loading/error/empty), `components/DataState.jsx` (one failure shape for every
panel), and a `bad` tone on the shared `Pill`.

`seed/engines.js` moved to `lib/engines.js` — it is provider labels and options,
configuration rather than a stand-in for a backend response.

## 3. The decisions that shaped it

**Loading is not zero.** `useResource` starts `loading: true` so no panel ever
renders `$0.00` before the first response lands. A billing screen that flashes
zero and then corrects itself teaches an operator to distrust it, and "no spend"
versus "not loaded" is exactly the distinction it must not blur.

**Errors are shown, never swallowed.** A failed request renders an error state
with a retry, and a 403 says something different from a network failure — an
operator on the wrong host needs to know that, not to press "try again" forever.
A table that silently renders nothing on failure is indistinguishable from a
month with no usage.

**Filtering moved to the server.** The prototype filtered a fixed array of ten
log lines in the browser. Over a real log that is not slow, it is *wrong*: a
client filter across the most recent 100 events answers "no warnings" when it
means "no warnings in the last 100 events".

**Suspension shows what the server committed.** `toggleTenant` replaces the row
with the response body rather than an optimistic guess, so a rejected write can
never leave the table displaying a suspension that did not happen.

**The sidebar stopped asserting "All systems operational".** It was hardcoded —
a claim the UI is in no position to make. It now reads the health aggregate every
60 seconds and says *"Status unavailable"* rather than *"fine"* when it cannot
reach the API. Failing dependencies render red, not amber: a down database shown
in warning colours reads as "slow".

**Metrics with no source were removed, not re-pointed.** The portal's "Avg.
resolution", "Assigned engineer" and "Resolved by AI" tiles had no backing
tables — A-008 removed ticketing and there is no engineer-assignment model. They
were replaced with counts the API actually returns. `/app/tickets` redirects to
the assistant so old bookmarks do not 404.

## 4. Found by running it

**`/platform/tenants/` would have 500'd on every single request.** The queryset
annotated `documents=Count("documents")`, but `TenantScopedModel` sets
`related_name="%(class)ss"`, so `documents` is already Tenant's reverse accessor
for `Document`. Django raises `ValueError: The annotation 'documents' conflicts
with a field on the model` at query-build time.

**The frontend build passed cleanly with this bug present.** So did the type
checker. It surfaced the moment a test called the endpoint — which is the entire
argument for writing the test before believing the screen.

**A wrong explanation from Phase 7A was corrected.** 7A recorded that
cross-tenant aggregation could not be tested because `MIRROR` made both aliases
share one app-role connection. Probing the connections directly disproved it:

```
default alias : user=mateassist_app  superuser=off
admin alias   : user=mateassist      superuser=on
same underlying connection object: False
```

The alias *is* a separate superuser connection; it simply cannot see uncommitted
writes. `test_platform_rollups.py` now runs with `transaction=True` and asserts
the real figures — including a regression test for the `status_for` alias bug —
so the claim is covered by the suite rather than only by a management command.
`test_the_admin_alias_really_is_a_superuser_connection` pins the premise so a
future misconfiguration fails legibly instead of returning zeros.

**RLS refused the new tests' fixture inserts.** `set_config(..., true)` is
transaction-scoped and `transaction=True` runs in autocommit, so the arming was
discarded before the INSERT and `WITH CHECK` rejected it — the same omission that
broke `ingest_demo` in Phase 5. Fixed with an explicit `transaction.atomic()`
around each write.

## 5. Honest limitations

- **Historical traffic still reads $0.00.** Cost is stored when a call is
  metered, so the eight calls made before prices existed are permanently
  unpriced. `seed_dev` now seeds rates and the UI names any model still missing
  one, but there is no backfill command (A-012).
- **The budget editor uses `window.prompt`.** Functional and honest, but it is
  not a designed form. A proper modal belongs with the subscription work.
- **Logs paginate to 100 rows with no "load more"**, and there is no live tail —
  the page polls only when you press Refresh.
- **`Conversation.resolved` is still never set true**, so the portal's
  "Resolved" state can currently only be reached by escalation. Carried since
  Phase 6 and still unaddressed.
- **No Celery worker was running during verification**, so health legitimately
  reported `degraded`. That is the UI telling the truth, but it means the
  `ok`-state banner was not exercised end-to-end.
- **None of these screens has been opened in a browser this phase.** Every
  endpoint they call is asserted live, field by field, but the rendering itself
  is verified only by the build and the radius lint.

## 6. Next

Phase 7 is complete; there is no dummy data left in either app. Remaining before
deployment:

- Open both apps in a browser and click through the rebuilt screens
- The screenshot paste path still has no live browser run (carried from Phase 6)
- Audit-log retention (D-114, deferred in A-012)
- Then: deployment, and the commercial track from A-011 — landing page, plans,
  trial, self-serve sign-up
