"""Federation adapters: vendor/protocol-specific camera source drivers.

`gov_catalogue.py` moved to `sentinel_core` (it only needs httpx + the shared
schemas, and core_api needs it for registry auto-onboarding without pulling
in edge_agent's OpenCV/ONNX Runtime/fast-alpr dependencies — see
docs/01-ARCHITECTURE.md section 4.1). This package is where the
docs-promised ONVIF and vendor-SDK-shim drivers (Milestone/Genetec/
Hikvision/Dahua) land in milestone M11; it stays a real Python package
(rather than being deleted) so that destination is already there.
"""

__all__: list[str] = []
