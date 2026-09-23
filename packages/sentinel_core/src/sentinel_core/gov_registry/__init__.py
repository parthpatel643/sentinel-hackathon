"""Government integration gateway — docs/01-ARCHITECTURE.md §6.4's
`ExternalRegistry` port and its four provider implementations. See
gov_registry/base.py for the port and gov_registry/resilience.py for the
retry/circuit-breaker/rate-limit machinery every provider shares."""

from sentinel_core.gov_registry.afis import AfisProvider
from sentinel_core.gov_registry.base import (
    AlertPushResult,
    ExternalRegistry,
    LicenceRecord,
    OperationNotSupportedError,
    PersonQuery,
    PersonRecord,
    RegistryAuditEvent,
    RegistryError,
    VehicleRecord,
)
from sentinel_core.gov_registry.egujcop import EGujCopProvider
from sentinel_core.gov_registry.sarthi import SarthiProvider
from sentinel_core.gov_registry.vahan import VahanProvider

__all__ = [
    "AfisProvider",
    "AlertPushResult",
    "EGujCopProvider",
    "ExternalRegistry",
    "LicenceRecord",
    "OperationNotSupportedError",
    "PersonQuery",
    "PersonRecord",
    "RegistryAuditEvent",
    "RegistryError",
    "SarthiProvider",
    "VahanProvider",
    "VehicleRecord",
]
