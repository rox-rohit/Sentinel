# Development Roadmap

The canonical roadmap is [`../DEVELOPMENT_ROADMAP.md`](../DEVELOPMENT_ROADMAP.md);
the live task board is [`../TASKS.md`](../TASKS.md).

Current state: Phases 0–3 and 5 are implemented and verified (22 backend tests,
clean typecheck, production build). Phase 4 is partially complete (anomaly
ensemble + explainability; forecasting and sequence models pending). Phase 6 has
the registry and drift; replay streaming and MLflow are pending. Phase 7 has all
twelve pages wired to real artifacts.

Next recommended tasks, in order:

1. Telemetry replay WebSocket service (pause/resume/speed, labelled simulated).
2. Sensor forecasting with chronological validation.
3. PyTorch sequence models once the environment allows (DECISIONS D-008).
4. MLflow tracking + retraining promotion workflow.
5. Portfolio release pack (architecture diagram, screenshots, demo script).
