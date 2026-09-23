"""Federation adapter framework — see drivers/base.py for the CameraSource
port and drivers/onvif.py for a concrete driver. The `rtsp` driver lives in
services/edge_agent/adapters/rtsp_driver.py instead of here: it depends on
OpenCV (edge_agent's capture pipeline), which this package deliberately
does not pull in (see this package's other consumers, e.g. core_api, which
must not need OpenCV/ONNX Runtime just to read a camera schema).

The `hikvision`/`dahua`/`milestone`/`genetec` drivers are contract-shaped
mocks per docs/01-ARCHITECTURE.md §4.1 and docs/07-DRIVER-SDK.md: real
protocol shape (auth flow, discovery call, stream URI negotiation) proven
against a mock server in tests/test_vendor_shims.py and
tests/test_driver_conformance.py, not a licensed vendor SDK integration."""

from sentinel_core.drivers.base import (
    CameraSource,
    DiscoveryScope,
    SourceHealth,
    StreamHandle,
    VendorEvent,
)
from sentinel_core.drivers.dahua import DahuaSource
from sentinel_core.drivers.genetec import GenetecSource
from sentinel_core.drivers.hikvision import HikvisionSource
from sentinel_core.drivers.milestone import MilestoneSource
from sentinel_core.drivers.onvif import OnvifSource

__all__ = [
    "CameraSource",
    "DahuaSource",
    "DiscoveryScope",
    "GenetecSource",
    "HikvisionSource",
    "MilestoneSource",
    "OnvifSource",
    "SourceHealth",
    "StreamHandle",
    "VendorEvent",
]
