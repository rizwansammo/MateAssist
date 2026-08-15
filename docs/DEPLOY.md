# Deploying MateAssist

Target: `mateassist.site` on MateServer (`169.58.114.252`), in `/opt/MateAssist`.

**MateServer already runs three people-facing applications** — MateDesk,
NetaMate and TalkRoom. Nothing here edits their configs, their containers or the
shared nginx site files. MateAssist adds one new site file, one new compose
project, and three loopback ports nobody else was using.

---

## What runs where

```
mateassist.site/                  holding page (marketing site, later)
mateassist.site/platform_admin    platform admin panel      -> 127.0.0.1:3011
mateassist.site/api/v1            API, platform scope       -> 127.0.0.1:8010
*.mateassist.site/                tenant portal             -> 127.0.0.1:3010
*.mateassist.site/api/v1          API, tenant scope         -> 127.0.0.1:8010
```

The admin panel is on a **path**, not a subdomain, because `IsPlatformOwner`
refuses any request that resolves to a tenant — and every subdomain does. The
apex is therefore the only host the platform surface can live on, and its root
is reserved for marketing.

Postgres, Redis and MinIO have **no host port at all**. The host itself already
runs a Postgres on 5432 and a Redis on 6379 for other apps; publishing ours
would collide with them.

## One-time setup

### 1. Secrets

```bash
mkdir -p /opt/MateAssist && cd /opt/MateAssist
# clone or copy the repo here
cp infra/.env.prod.example infra/.env && chmod 600 infra/.env
```

Fill every blank. Generate each with `openssl rand -base64 36`, and do not reuse
a value between two of them.

Two that matter more than the rest:

- **`APP_DB_PASSWORD`** — the NOSUPERUSER role all tenant traffic uses. Without
  it the app connects as the owner, PostgreSQL exempts superusers from RLS
  unconditionally, and every isolation policy enforces nothing while appearing
  to be in place.
- **`MATEASSIST_VAULT_KEY`** — the AES-256-GCM key encryption key. Losing it
  orphans every stored provider credential. Back it up somewhere that is not
  this server.

`MATEASSIST_ALLOW_DEMO_DATA` is deliberately absent. Its absence is what stops
`seed_dev`, `ingest_demo` and `seed_runbooks` writing fabricated tenants and a
"VPN Runbook (demo)" into a customer's workspace.

### 2. Wildcard certificate

The certificate must cover `*.mateassist.site`, and a wildcard can only be
issued through DNS-01 — `--nginx`, webroot and standalone cannot do it.

```bash
cat > /root/.cloudflare-mateassist.ini <<'EOF'
dns_cloudflare_api_token = <token scoped to the mateassist.site zone>
EOF
chmod 600 /root/.cloudflare-mateassist.ini

certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /root/.cloudflare-mateassist.ini \
  --dns-cloudflare-propagation-seconds 30 \
  -d mateassist.site -d '*.mateassist.site' \
  --cert-name mateassist.site
```

A separate credentials file from the other domains, with a token scoped to this
zone only, so a mistake here cannot touch `matedesk.pro`'s DNS.

Renewal is unattended via the existing `certbot.timer`. Check it occasionally:

```bash
certbot renew --dry-run
```

### 3. nginx

```bash
cp infra/nginx/mateassist.site /etc/nginx/sites-available/mateassist.site
ln -s /etc/nginx/sites-available/mateassist.site /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

`nginx -t` before reload, always. A syntax error takes down the other three
applications, not just this one.

## Deploying

Images are built by GitHub Actions on a version tag and published to GHCR.

```bash
git tag v1.0.0 && git push origin v1.0.0     # from your machine
```

Then on the server:

```bash
cd /opt/MateAssist/infra
docker compose -f docker-compose.prod.yml --env-file .env pull
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

**Deployment is automatic.** A push to `main` builds the three images and
deploys them: the `.env` image tags are rewritten to the new build, the
containers are pulled and restarted, migrations run on the `admin` connection,
and the four public endpoints are polled until they answer 200 - the job fails
and prints the backend log if they do not.

The commands above are the manual equivalent, kept for a rollback or when the
pipeline itself is broken.

This page previously claimed manual deployment was a deliberate safeguard,
because MateServer also runs three other people-facing applications. That
concern is real but the safeguard was not: the deploy only ever touched
MateAssist's own compose project, and the tag rewrite is scoped by a regex to
`mateassist-*` images. The honest reason it was manual is that it was never
finished after the first deploy.

Version tags still work and still produce a tagged image. They now MARK a
release rather than cause one.

### Migrations

```bash
docker compose -f docker-compose.prod.yml --env-file .env \
  exec backend python manage.py migrate --database=admin
```

`--database=admin` is required. The default connection is the deliberately
under-privileged app role and cannot create RLS policies.

### First deploy only — provision

```bash
docker compose -f docker-compose.prod.yml --env-file .env \
  exec backend python manage.py provision
```

Creates the platform owner, the workspace, its users and the model price rows —
and nothing else. Idempotent, so it is safe on every deploy; existing accounts
keep their passwords unless `--reset-passwords` is passed.

### Then, in the browser

1. Sign in at `mateassist.site/platform_admin`
2. **AI Configuration** → add a provider key for each engine. There is no key in
   the vault, so until this is done the assistant correctly reports that it
   cannot answer.
3. Sign in to the workspace portal as the tenant admin and upload real runbooks.

Until a runbook is indexed, every answer will honestly say nothing matched.
That is correct behaviour, and it looks broken if you are not expecting it.

## Verifying

```bash
curl -s https://mateassist.site/api/v1/health/ | jq .status
curl -sI https://netamate.mateassist.site/ | head -1
docker compose -f docker-compose.prod.yml --env-file .env ps
```

Health reports `degraded` rather than `ok` when Celery has no workers attached —
that is the check telling the truth, not a fault.

The one worth doing by hand: **sign in on a tenant subdomain**. Tenant identity
comes from the Host header, and a proxy that rewrites it produces "invalid
credentials" on every tenant login while the admin surface keeps working
perfectly. That asymmetry is why it hid during development (A-007).

## Rolling back

```bash
# in infra/.env, pin the previous tag
MATEASSIST_BACKEND_IMAGE=ghcr.io/rizwansammo/mateassist-backend:v0.9.0
...
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

Pin version tags rather than `latest` when you want to know what is running.
`latest` is convenient and tells you nothing after the fact.

Note that migrations are **not** rolled back by this. Reverting a deployment
that ran a destructive migration needs a database restore, which is why
migrations that drop columns deserve a separate, deliberate release.

## Logs

```bash
docker compose -f docker-compose.prod.yml --env-file .env logs -f backend
docker compose -f docker-compose.prod.yml --env-file .env logs -f celery_worker
```

Provider failures are also written to the audit log and visible in the platform
admin panel under System Logs — including the real error text that users never
see (D-135).
