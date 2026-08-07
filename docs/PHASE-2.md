# Phase 2 — Identity, Tenancy & Isolation

**Status: COMPLETE.** The D-025 gate is green.

---

## 1. The gate

D-025 required a test that bypasses the ORM with raw SQL and is *still* denied
cross-tenant rows by PostgreSQL. `apps/tenancy/tests/test_isolation.py` — 9 tests,
all passing:

| Test | Proves |
|---|---|
| `test_connection_role_cannot_bypass_rls` | the premise — the app role is not superuser and has no BYPASSRLS |
| `test_policy_is_enabled_and_forced` | RLS is ENABLEd **and** FORCEd, so the table owner is not exempt |
| `test_orm_sees_only_the_current_tenant` | the manager scopes correctly |
| `test_bypassing_the_tenant_manager_...` | `all_objects`, which skips the manager, still cannot cross |
| **`test_raw_sql_cannot_cross_tenants`** | **the gate** — bare `SELECT` with no `WHERE` returns only one tenant |
| `test_explicit_cross_tenant_query_...` | naming another tenant's id explicitly returns nothing |
| `test_unset_context_exposes_no_tenant_rows` | fail closed: unset means "no tenant", never "all tenants" |
| `test_cannot_write_into_another_tenant` | `WITH CHECK` — isolation is not read-only |
| `test_platform_rows_are_invisible_...` | a workspace cannot enumerate platform staff |

**35 backend tests pass** overall; `check` and `makemigrations --check` clean.

---

## 2. The thing that made the gate real

Our container's `POSTGRES_USER` is a **superuser**, and PostgreSQL exempts
superusers from RLS unconditionally. Had the application kept connecting as it,
every policy would have been decorative and all nine tests above would have
passed while proving nothing.

So Phase 2 introduced a second role and a second alias:

```
default -> mateassist_app   NOSUPERUSER   all tenant traffic, subject to policy
admin   -> mateassist       superuser     migrations + platform-admin surface
```

`infra/scripts/setup-app-role.ps1` creates it and **verifies** the role cannot
bypass RLS before reporting success. `test_connection_role_cannot_bypass_rls`
asserts the same thing from inside the suite, so the premise cannot rot silently.

`FORCE ROW LEVEL SECURITY` matters as much as `ENABLE`: in the pytest database
the app role owns the tables it migrated, and an owner is exempt without FORCE.

Migrations run as the owner: `manage.py migrate --database=admin`.

---

## 3. How isolation is armed

`SubdomainMiddleware` resolves `Host` → `Tenant`, then opens an explicit
transaction and sets `app.tenant_id` with `set_config(..., is_local => true)`.
Transaction-scoped, so the variable and the work share a lifetime and nothing
leaks onto a pooled connection.

The policy predicate:

```sql
CASE WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
     ELSE tenant_id = app_current_tenant_id() END
```

Used for both `USING` and `WITH CHECK`. Unset context admits only platform-level
rows — which is exactly what lets a PLATFORM_OWNER authenticate on the admin host
while remaining unable to read any workspace's data.

`tenancy_tenant` is deliberately **not** policy-protected: it is the registry of
workspaces, not data belonging to one.

---

## 4. Authentication

- Access token 15 min, returned in the body, held **in memory only** (D-031)
- Refresh token 7 days in an **httpOnly** cookie scoped to `/api/v1/auth`,
  never in a response body (D-032) — asserted by test and confirmed live
- Rotation + blacklist: a stolen refresh token is usable at most once
- **Membership is re-checked on every refresh**, so revoking access bites within
  the access-token lifetime rather than at next login
- Every failure mode — wrong password, unknown user, not-a-member — returns an
  identical response, so the login form cannot be used to enumerate a workspace's
  staff. There is a test that asserts the three responses are byte-identical.

Live, against the running server:

```
login   rizwan@netswitch.test  on netswitch.localhost   -> 200, tenant=netswitch
login   same credentials       on apptriangle.localhost -> 400 Invalid credentials
me      netswitch token        on netswitch.localhost   -> 200
me      netswitch token        on apptriangle.localhost -> 403 Not a member
login   any credentials        on nosuch.localhost      -> 404 Unknown workspace
```

The tenant is re-resolved from the Host header on every request, so a validly
signed, unexpired token grants nothing on another workspace. Token claims are a
client convenience and never the basis for an access decision.

---

## 5. Frontend

- `AuthProvider` restores the session on mount via the refresh cookie — memory-only
  access tokens mean a page reload always starts with none, and the cookie is what
  makes "still signed in after F5" work without exposing a long-lived credential
- `apiFetch` retries once on 401 after refreshing; concurrent 401s share a single
  refresh promise, because rotation would otherwise let parallel refreshes
  invalidate the session they were trying to save
- `RequireAuth` guards routes, with a `restoring` state so a reload does not flash
  the login screen
- The workspace field on the login form is now **read-only** — the workspace comes
  from the Host header, not from user input
- New admin login page: the prototype had none, and the platform host admits only
  PLATFORM_OWNER

---

## 6. Dev data

```
python manage.py seed_dev --database=admin
```

Password for every account: `MateAssist!2026`

| Account | Host |
|---|---|
| `owner@mateassist.io` | admin host (no subdomain) |
| `admin@netswitch.test`, `rizwan@netswitch.test` | `netswitch.*` |
| `admin@apptriangle.test`, `rizwan@apptriangle.test` | `apptriangle.*` |

---

## 7. Carried forward

- **A-007 is still open.** `*.localhost` does not resolve outside a browser, so
  tests set `HTTP_HOST` explicitly and live checks use `curl -H "Host: ..."`.
  That works, but browsing the portal on a tenant subdomain still needs a hosts
  entry or a wildcard DNS service. The decision belongs with whoever runs it.
- **Role enforcement is modelled, not yet enforced per-endpoint.** `Membership.role`
  exists and is returned in the session; DRF permission classes keyed on it arrive
  with the endpoints that need them in Phase 3.
- Tenant provisioning from the admin UI is still a toast saying it lands in Phase 2 —
  the API exists via `seed_dev`, the UI button does not yet call it.

## 8. Next — Phase 3

Helpdesk domain: `Ticket`, `Category`, `Queue`, SLA, the status state machine, and
per-tenant sequential numbering by database sequence (D-120). Every model inherits
`TenantScopedModel` and gets the same RLS treatment as `tenancy_membership` —
including its own isolation test.
