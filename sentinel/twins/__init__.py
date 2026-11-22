"""Digital-twin ingestion, scoring and auto feed."""

from sentinel.twins.service import TwinService, get_twin_service, sensor_catalog

__all__ = ["TwinService", "get_twin_service", "sensor_catalog"]
