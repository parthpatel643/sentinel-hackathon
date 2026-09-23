# 07 · Federation Driver SDK

*Companion to [01-ARCHITECTURE.md §4.1](./01-ARCHITECTURE.md#41-federation-adapter-framework-model-3).
This document exists because M11's exit criterion is "onboarding department
27 is a driver, not a release — demonstrated, not asserted." What follows is
the demonstration: a real interface, two real drivers against it, and a
conformance suite that runs the same contract against both.*

---

## 1. The port

Every camera source — no matter the protocol or vendor — implements one
`Protocol`:

```python
# packages/sentinel_core/src/sentinel_core/drivers/base.py
class CameraSource(Protocol):
    driver_id: str
    capabilities: SourceCapabilities

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]: ...
    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle: ...
    async def health(self, camera: CameraDescriptor) -> SourceHealth: ...
```

- `discover` finds cameras — either a directed probe at one known host, or
  (protocol permitting) a broadcast/multicast scan of a network.
- `open` resolves a stream profile into something a player/relay can
  actually consume (a URL + protocol, today; nothing here prevents a
  future driver returning a live socket instead).
- `health` answers "is this camera reachable right now," independent of
  whether anything is actively streaming from it.
- `capabilities` is a `SourceCapabilities` value the UI reads directly to
  grey out actions a given camera's driver genuinely can't do (e.g. PTZ
  controls on a plain RTSP-only camera) — see docs/03-UX-DESIGN.md's
  capability matrix.

## 2. Drivers shipped

| Driver | File | Status |
|---|---|---|
| `rtsp` | `services/edge_agent/src/edge_agent/adapters/rtsp_driver.py` | Real — implements `CameraSource`, wrapping the M1 capture pipeline (`pipeline/capture.py`) that has driven this project's synthetic grid since the beginning. |
| `onvif` | `packages/sentinel_core/src/sentinel_core/drivers/onvif.py` | Real — implements `CameraSource` via WS-Discovery (UDP multicast probe, with a directed-host fallback that's the reliable path on segmented CCTV networks), `GetDeviceInformation`, `GetProfiles`/`GetStreamUri`, and PTZ `ContinuousMove`/`Stop`. Hand-rolled SOAP/XML (no WSDL-based client library), with real WS-Security UsernameToken digest auth — not HTTP Basic, which most ONVIF devices reject. |
| *(gov catalogue)* | `packages/sentinel_core/src/sentinel_core/gov_catalogue.py` | Real, but **not** a `CameraSource` — a separate, simpler discovery-only client (list cameras + bulk-import) predating this Protocol, already wired into the onboarding wizard's "Connect a department system" step. Left as-is rather than force-fit into `CameraSource`, since it has no stream-open/health-check responsibility of its own (cameras it discovers are onboarded as plain `rtsp` sources). |
| `milestone` / `genetec` / `hikvision` / `dahua` | *(M11, in progress)* | Contract-shaped mock(s); see the vendor-shim section once built. |

## 3. Why ONVIF is hand-rolled SOAP, not a WSDL client library

Libraries like `python-onvif-zeep` generate their client from bundled WSDL
files, which then need to be kept in sync with whichever ONVIF profile
version a given camera implements. For the handful of operations this
driver actually needs (device info, media profiles, stream URI, two PTZ
calls), constructing and parsing the XML directly means:

1. No WSDL files to vendor and update.
2. The entire wire protocol is visible in one file — useful for a jury (or
   a future maintainer) who wants to see *exactly* what "ONVIF support"
   means here, not trust an opaque code-generation step.
3. WS-Security digest auth (`SHA1(nonce + created + password)`, base64) is
   implemented with real cryptographic primitives (`hashlib`, `secrets`),
   not stubbed — see `_wsse_header()`.

## 4. Testing without a physical camera

`packages/sentinel_core/tests/test_onvif_driver.py` runs the driver against
an inlined mock ONVIF device (an `httpx.MockTransport` handler) that:

- Serves realistic canned SOAP responses for each operation.
- **Recomputes the WS-Security digest itself** and rejects a request whose
  password doesn't match — proving the auth path is exercised for real,
  not just "does the code run without crashing."

`services/edge_agent/src/edge_agent/adapters/rtsp_driver.py` reuses the
same `RtspCapture`/`VideoSource` test-double pattern the capture pipeline's
own tests already established (`FakeVideoSource`), via an injectable
`backend_factory` constructor argument.

## 5. The conformance suite

`tests/test_driver_conformance.py` runs the **same five contract checks**
against every driver in `_DRIVER_CASES`, parametrized:

1. `discover()` with a valid scope returns at least one camera with at
   least one stream profile that has a URL.
2. `discover()` with an empty/unreachable scope returns an empty list —
   **never raises**. (This caught a real bug during development: the ONVIF
   driver's multicast probe raised `OSError` on a network where multicast
   is unreachable, which is common on segmented CCTV networks. Fixed to
   degrade to an empty result instead of crashing — see the driver's
   `probe_multicast()` docstring.)
3. `health()` of a just-discovered camera reports `LIVE`.
4. `open()` returns a `StreamHandle` whose URL/protocol match the profile
   passed in.
5. `capabilities` is genuinely declared (not inherited/defaulted) per
   driver.

Adding driver #3 to this suite is one new `DriverCase(...)` entry — that
line is the actual evidence for "a driver, not a release."

## 6. Adding a new driver (the "department 27" walkthrough)

1. Implement `CameraSource`'s three async methods for the new
   protocol/vendor SDK, plus `driver_id` and `capabilities`.
2. If there's no live device to test against, mock it: an `httpx.
   MockTransport` handler (SOAP/REST) or an injectable backend factory
   (SDK client) — whichever matches how the real thing talks over the
   wire. Both existing drivers show a worked example of each style.
3. Add one `DriverCase` entry to `tests/test_driver_conformance.py`.
   Passing the five shared contract checks is the bar for "this driver is
   real," independent of anything vendor-specific.
4. Register the driver's `driver_id` wherever cameras are onboarded
   (registry `CameraCreate.driver_id`, or catalogue-driven discovery) —
   no other part of the system needs to change; every consumer of a
   camera already only depends on `CameraDescriptor`/`StreamProfile`, not
   on which driver produced them.
