# SENTINEL — Azure deployment

The public deployment runs the FastAPI service on Azure App Service, the React
console on Azure Static Web Apps and the operational store on Azure Database for
PostgreSQL Flexible Server. The console still falls back to the exported artifact
snapshot when the API is unreachable.

## Live hosts

| Component | Host |
|---|---|
| API | https://sentinel-api-l1fit9.azurewebsites.net |
| API docs | https://sentinel-api-l1fit9.azurewebsites.net/docs |
| Console | https://victorious-sky-062450900.3.azurestaticapps.net |
| PostgreSQL | `sentinel-pg-c286gh.postgres.database.azure.com` (database `sentinel`, user `sentineladmin`) |

All Azure resources live in resource group `sentinel-rg`. The App Service plan is
`sentinel-plan` (B1, Linux, `centralindia`); the Static Web App is
`sentinel-console-l1fit9` (`eastasia`); PostgreSQL is `sentinel-pg-c286gh`
(Flexible Server, B1ms, PostgreSQL 16, `eastasia`).

## Application settings (App Service)

| Name | Value |
|---|---|
| `SENTINEL_DATABASE_URL` | `postgresql://sentineladmin:<password>@sentinel-pg-c286gh.postgres.database.azure.com:5432/sentinel?sslmode=require` |
| `SENTINEL_SEED_DB` | `/home/site/wwwroot/artifacts/sentinel.db` |
| `SENTINEL_CORS_ORIGINS` | `https://victorious-sky-062450900.3.azurestaticapps.net` |
| `WEBSITES_PORT` | `8000` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
| `SENTINEL_API_KEY` | Operator key for mutating routes (set it; do not commit it) |
| `SENTINEL_REQUIRE_API_KEY` | `true` to fail closed if the key is missing |
| `SENTINEL_RATE_LIMIT_PER_MINUTE` | `300` per client and route prefix (optional) |

The console sends `X-API-Key` from its **session** storage (System Settings →
Access control); the key never enters the bundle. Device telemetry uses a
separate per-device token issued by `POST /api/v1/devices` and stored only as a
PBKDF2 digest. Twin auto mode runs as a thread inside the single uvicorn
process that `startup.sh` launches — keep the app at one worker, or move the
feeder to a queue before scaling out.

The database password is only in the App Service setting; it is not committed.
`config.py` rewrites `postgres://` / `postgresql://` to the psycopg 3 driver,
which is installed from `requirements.txt`.

The startup command is:

```
/bin/bash /home/site/wwwroot/startup.sh
```

`startup.sh` uses the App Service runtime Python (`/opt/python/3.15.2`) with the
site-packages extracted from the Oryx build, seeds the store from the packaged
SQLite registry, and starts uvicorn on `$PORT` (8000).

## Continuous deployment (GitHub Actions)

`.github/workflows/ci.yml` has two jobs:

1. **`verify`** — the required gate. Runs on every push and pull request:
   datasets, pipeline build, `pytest`, worker tests, typecheck and console build.
2. **`deploy`** — runs only for pushes to `main` (or a manual
   `workflow_dispatch` from `main`), and only when `verify` succeeded in the same
   run (`needs: verify`). It deploys the API first, waits for `/health`, then
   deploys the console and smoke-checks both.

`verify` uploads `artifacts/`, `data/processed/` and
`src/generated/snapshot.json` as a one-day artifact because those paths are
Git-ignored; the deploy job downloads them, so the deployed models are exactly
the ones the tests ran against.

### Required repository secrets

Settings → Secrets and variables → Actions → **Repository secrets**. Nothing else
is needed: hosts and app names are plain `env` values in the workflow.

| Secret | Used by | How to obtain it |
|---|---|---|
| `AZURE_API_PUBLISH_PROFILE` | `azure/webapps-deploy@v3` | `az webapp deployment list-publishing-profiles -g sentinel-rg -n sentinel-api-l1fit9 --xml` |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | `Azure/static-web-apps-deploy@v1` | `az staticwebapp secrets list -g sentinel-rg -n sentinel-console-l1fit9 --query properties.apiKey -o tsv` |

Both commands print deployment credentials. Paste them into the secret form, never
into a commit, a log or a workflow file. Resetting either credential, or
recreating the resource, invalidates the secret: update it immediately, because
the deploy job reads both at run time and fails before deploying if either is
missing.

`AZURE_API_PUBLISH_PROFILE` is the complete XML document, not the password alone.

### What the deploy job does

1. Installs frontend dependencies and downloads the verified artifacts.
2. Rebuilds the console with
   `VITE_API_BASE_URL=https://sentinel-api-l1fit9.azurewebsites.net/api/v1`.
3. Copies `deployment/staticwebapp.config.json` into `dist/client` (SPA fallback
   and response headers).
4. Stages the API package — `sentinel/`, `requirements.txt`, `startup.sh`,
   `artifacts/` and `data/processed/` — and zip-deploys `stage/`.
5. Uploads `dist/client` to Static Web Apps as a prebuilt app
   (`skip_app_build: true`).
6. Runs the smoke checks below and fails the run on any mismatch.

Only the API is built remotely: `SCM_DO_BUILD_DURING_DEPLOYMENT=true` (already on
the app) makes Oryx install `requirements.txt` into `antenv`, and the custom
startup command runs `startup.sh` against that directory. A virtualenv cannot be
shipped from the runner — runners are Python 3.12 and the app runs 3.15, so the
binary wheels (numpy, pandas, pyarrow, psycopg) would not load. If the App
Service Python runtime version ever changes, `startup.sh` (`SITE_PACKAGES`) must
change with it.

### Smoke checks

- `GET /api/v1/health` returns 200, polled for up to 6 minutes (cold start).
- `GET /api/v1/{fleet/summary, alerts?limit=5, models, datasets}` return 200.
- CORS preflight from the console origin returns 200 with the matching
  `Access-Control-Allow-Origin`.
- The console serves `/` and an unknown route (`/fleet`) with the SPA shell.

### One-time setup

1. Add both repository secrets above.
2. Protect `main`: require the **Tests, typecheck and build** check and block
   force-pushes. The deploy job cannot start unless that job passed in the same
   run, but branch protection also keeps an unverified merge off `main`.
3. Run **Actions → CI → Run workflow** from `main` once and watch it. The first
   run replaces the hand-assembled `wwwroot`; if the health poll fails, read
   `/home/site/wwwroot/startup-debug.log` through Kudu before retrying.

After that, every merge to `main` deploys once tests and the pipeline build
succeed (roughly 10–15 minutes). A failed smoke check fails the workflow but does
not roll back; re-run the workflow on the last good commit, or fall back to the
manual procedure below.

## Deploying an update (manual fallback)

Use this only when Actions cannot run (for example while the deployment
credentials are being rotated).

### API

1. Build/verify locally (`python -m pytest -q`).
2. Upload the changed files under `/home/site/wwwroot` (Kudu VFS or a fresh zip
   deployment). If a full Oryx zip is used, let Oryx finish and keep its
   `output.tar.zst` until after startup has generated its script.
3. Do **not** delete `output.tar.zst` while `oryx-manifest.toml` still declares
   `CompressDestinationDir="true"`. Oryx re-extracts that archive on every
   container start; if it is missing, startup panics with
   `zstd/gzip output not found` and never runs the app command. After manually
   extracting the archive, remove `oryx-manifest.toml` so Oryx generates the
   startup script directly.
4. Set the startup command above, then restart the app.
5. Wait for `/api/v1/health` to return 200. A first database request after a cold
   start can take several seconds while psycopg opens its pool.

### Console

```bash
VITE_API_BASE_URL=https://sentinel-api-l1fit9.azurewebsites.net/api/v1 bun run build
cp deployment/staticwebapp.config.json dist/client/
npx @azure/static-web-apps-cli deploy dist/client \
  --deployment-token "$(az staticwebapp secrets list -g sentinel-rg \
    -n sentinel-console-l1fit9 --query properties.apiKey -o tsv)" \
  --env production
```

## Database

The store is seeded idempotently at startup from `artifacts/sentinel.db`:
datasets, model registry entries and alerts are copied only when the target is
empty. Current hosted contents: 2 datasets, 14 model versions, 34 alerts.

PostgreSQL firewall: allow Azure services, plus a temporary client IP rule only
while running the seed/admin locally. Remove temporary rules afterwards.

## Verification performed

- `GET /api/v1/health` → 200.
- `GET /api/v1/fleet/summary` → 200 (100 assets); `/alerts` → 34; `/models` → 14;
  `/datasets` → 2.
- CORS preflight from the Static Web App origin → 200 with the matching
  `Access-Control-Allow-Origin`.
- Console loaded the live API: all fleet payload requests 200 and “Live
  inference service” shown.
- Offline fallback: with `fetch` forced to fail, reloading showed “Exported build
  artifacts” and the packaged snapshot. The earlier pre-API deployment also
  served the console with the API absent.

The GitHub Actions `deploy` job repeats the health, read, CORS and console checks
automatically after each push to `main`.
