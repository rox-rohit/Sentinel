"""API route modules."""

from sentinel.api.routes import (alerts, catalog, decisions, devices, fleet, health,
                                 onboarding, predictions, replay)

ROUTERS = [
    health.router,
    fleet.router,
    predictions.router,
    decisions.router,
    catalog.router,
    replay.router,
    alerts.router,
    onboarding.router,
    devices.router,
]

__all__ = ["ROUTERS"]
