# SENTINEL — Persistent Agent Instructions

You are continuing a long-running product build. **Never start over.** Every session
resumes from the last verified milestone in this repository.

## 0. Read order at the start of every session

1. `AGENTS.md` (this file)
2. `PROJECT_VISION.md` — product scope and non-negotiable principles
3. `DEVELOPMENT_ROADMAP.md` — phases and current phase
4. `TASKS.md` — completed / in-progress / pending work
5. `DECISIONS.md` — architectural decisions already made (do not re-litigate)
6. `docs/` — architecture and methodology detail
7. Inspect the actual repository: `git status`, `git log --oneline -5`,
   `sentinel/`, `src/`, `tests/`

Then run the verification gates before changing anything:

```bash
python -m pytest -q                 # backend + data + model tests
bun run typecheck                   # frontend types
bun run build                       # frontend + worker build
```

A task is only "done" when its code exists, tests pass, and `TASKS.md` says so.
Documentation is a claim; code and tests are the evidence.

## 1. What this project is

SENTINEL — Industrial Intelligence & Predictive Maintenance Platform.
Python data-science backend + FastAPI + Vite/React/TypeScript command centre.
The full vision is in `PROJECT_VISION.md`. Read it before designing anything.

## 2. Layout

```
sentinel/            Python package (data, features, models, decision, inference, api, store)
  data/              dataset adapters, validation, preprocessing
  features/          leakage-safe feature pipeline
  eda/               dataset-driven exploratory analysis
  models/            classical ML, RUL, anomaly, explainability, evaluation, artifacts
  decision/          health scoring, maintenance optimisation
  inference/         model-backed services (no HTTP logic)
  api/               FastAPI routers, schemas, dependencies
  store/             SQLAlchemy operational metadata store
  pipelines/         reproducible build/export entry points
artifacts/           trained models, metrics, registry db, exported snapshot
data/raw/            source datasets (git-ignored, fetched by scripts/fetch_data.py)
data/processed/      parquet outputs (git-ignored)
src/                 React command centre (design system + pages)
docs/                architecture, methodology, dataset and evaluation documents
tests/               pytest backend suite + bun frontend/worker tests
```

## 3. Non-negotiable engineering rules

- No hardcoded predictions, metrics, health scores or random dashboard numbers.
  Every displayed value comes from an artifact produced by the Python pipeline,
  or is explicitly labelled as a demonstration fixture.
- No placeholder core ML modules. If a module is not implemented, mark it
  `planned` in `TASKS.md` and do not expose it as working in the UI.
- Never leak future information into features (no centered windows, no
  shuffling of time series, no split that shares an engine/machine between
  train and test).
- Report held-out metrics, never training metrics, as performance.
- Accuracy alone is never the selection metric.
- Distinguish model attribution (SHAP) from physical causation.
- Keep HTTP routing, inference and model logic in separate layers.
- Do not commit data files, model binaries or secrets. `.gitignore` covers them.
- Preserve working code; extend instead of rewriting unless a decision in
  `DECISIONS.md` records why a rewrite is required.
- Update `TASKS.md` and `DEVELOPMENT_ROADMAP.md` after every milestone, and
  regenerate the platform snapshot when models or outputs change:
  `python -m sentinel.pipelines.build`.

## 4. Environment facts (verified 2026-11-14, Windows host)

- Python 3.15.0, `pip` available as `python -m pip`.
- Installed and verified: numpy 2.5.4, pandas 3.1.0, scipy 1.18.1,
  scikit-learn 1.9.1, xgboost 3.4.1, matplotlib 3.11.2, pyarrow 26.0.0,
  fastapi, pydantic 2, sqlalchemy 2, pytest 8.3.4, joblib.
- Node 24.21.0, npm 11.19.0, bun. Frontend: Vite + React 19 + TS + Tailwind 4
  + Recharts + Cloudflare Worker (template origin: this repo started from a
  Freebuff Vite starter, since repurposed).
- GPU: NVIDIA RTX 3050 Laptop, 4 GB. CUDA PyTorch is **not** installed; free
  disk is ~3.5 GB, so deep-learning dependencies are deferred (see `TASKS.md`).
- Databases: SQLite is the local fallback; the store layer is SQLAlchemy and
  honours `SENTINEL_DATABASE_URL` for PostgreSQL.

## 5. Commands

```bash
python -m sentinel.pipelines.build          # data -> features -> models -> artifacts -> snapshot
python -m pytest -q                         # backend tests
python -m uvicorn sentinel.api.main:app --port 8000    # API + OpenAPI docs at /docs
bun run dev                                 # frontend on http://localhost:5173
bun run typecheck                           # TS gate
bun run build                               # production build
```

The frontend reads live API data when the backend is reachable and otherwise
falls back to the exported artifact snapshot, surfacing that state in the UI.

## 6. Session close-out

1. Run the gates above.
2. Update `TASKS.md` (what is verified done / in progress / next).
3. Update `DEVELOPMENT_ROADMAP.md` if a phase moved.
4. Add a `DECISIONS.md` entry for any architectural choice with alternatives.
5. Commit the working state when the user has authorised commits. Do not add AI
   attribution footers, "Generated with" lines or co-author trailers: the
   repository owner asked for commits to carry only their authorship.
6. Report: implemented, files touched, tests run and their result, unfinished
   work, recommended next task.
