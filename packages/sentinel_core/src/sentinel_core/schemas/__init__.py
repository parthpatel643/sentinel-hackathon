"""Domain schemas shared across every plane of the platform."""

from sentinel_core.schemas.camera import (
    AnalyticsTier,
    CameraDescriptor,
    CameraStatus,
    GeoPoint,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)
from sentinel_core.schemas.events import (
    SCHEMA_VERSION,
    AnprPayload,
    BoundingBox,
    Event,
    EventType,
    EvidenceRef,
    HealthPayload,
    PipelineProvenance,
    VehicleAttributes,
    new_event_id,
)

__all__ = [
    "SCHEMA_VERSION",
    "AnalyticsTier",
    "AnprPayload",
    "BoundingBox",
    "CameraDescriptor",
    "CameraStatus",
    "Event",
    "EventType",
    "EvidenceRef",
    "GeoPoint",
    "HealthPayload",
    "PipelineProvenance",
    "SourceCapabilities",
    "StreamProfile",
    "StreamProtocol",
    "VehicleAttributes",
    "new_event_id",
]
