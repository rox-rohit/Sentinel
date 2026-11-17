# SENTINEL documentation index

Canonical project documents live at the repository root; the `docs/` folder
holds the detailed technical documents.

## Root

| File | Purpose |
|---|---|
| [`../PROJECT_VISION.md`](../PROJECT_VISION.md) | Product scope, six core questions, module status |
| [`../SYSTEM_ARCHITECTURE.md`](../SYSTEM_ARCHITECTURE.md) | Layers, runtime topology, module boundaries |
| [`../DEVELOPMENT_ROADMAP.md`](../DEVELOPMENT_ROADMAP.md) | Phase-by-phase status |
| [`../TASKS.md`](../TASKS.md) | Authoritative task board and limitations |
| [`../DECISIONS.md`](../DECISIONS.md) | Architecture decision record |
| [`../AGENTS.md`](../AGENTS.md) | Session instructions and verification gates |

## docs/

| File | Purpose |
|---|---|
| [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) | Ingestion, validation, schemas, storage, versioning |
| [`DATASET_DOCUMENTATION.md`](DATASET_DOCUMENTATION.md) | Sources, structure, licences, data-quality findings |
| [`ML_METHODOLOGY.md`](ML_METHODOLOGY.md) | Leakage control, feature design, model protocols |
| [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md) | Measured results, confusion matrices, threats to validity |
| [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) | Verified runs, rejected hypotheses, corrections |
| [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) | Endpoints, payloads, errors, auth |
| [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) | Tokens, components, chart and layout rules |
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Pointer to the canonical root architecture |
| [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) | Pointer to the canonical root roadmap |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Azure hosts, environment variables, update procedure and deployment checks |

## Reproduce

```bash
python scripts/fetch_data.py
python -m sentinel.pipelines.build
python -m pytest -q
python -m uvicorn sentinel.api.main:app --port 8000
bun run dev
```
