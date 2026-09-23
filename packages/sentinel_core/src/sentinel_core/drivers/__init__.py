"""Federation adapter framework — see drivers/base.py for the CameraSource
port and drivers/onvif.py for a concrete driver. The `rtsp` driver lives in
services/edge_agent/adapters/rtsp_driver.py instead of here: it depends on
OpenCV (edge_agent's capture pipeline), which this package deliberately
does not pull in (see this package's other consumers, e.g. core_api, which
must not need OpenCV/ONNX Runtime just to read a camera schema)."""

from sentinel_core.drivers.base import (
    CameraSource,
    DiscoveryScope,
    SourceHealth,
    StreamHandle,
    VendorEvent,
)
from sentinel_core.drivers.onvif import OnvifSource

__all__ = [
    "CameraSource",
    "DiscoveryScope",
    "OnvifSource",
    "SourceHealth",
    "StreamHandle",
    "VendorEvent",
]
