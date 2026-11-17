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

## Deploying an update

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
