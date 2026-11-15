"""API route modules."""

from sentinel.api.routes import catalog, decisions, fleet, health, predictions, replay

ROUTERS = [
    health.router,
    fleet.router,
    predictions.router,
    decisions.router,
    catalog.router,
    replay.router,
]

__all__ = ["ROUTERS"]
