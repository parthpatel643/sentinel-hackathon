"""Infrastructure lifecycle report — the "ageing infrastructure" and
"maintenance-status monitoring" halves of Model 1's gap analysis, next to
`gap_analysis.py`'s spatial half.

Lifecycle facts live in a camera's `attributes` (the registry's free-form
metadata, already carried by every onboarding path) under the keys in
`LIFECYCLE_ATTRIBUTES`, rather than in dedicated columns: departments supply
them unevenly — the Food & Civil Supplies register may have installation
dates and nothing else, a municipal AMC register only expiry dates — and a
report that counts what is *unknown* is more honest than a schema that
forces a value.

Private cameras (societies, malls, shops) are onboarded only "wherever
feasible and permitted", so they carry `ownership=private`, the consent
reference they were onboarded under and when it lapses. A private camera
without current consent is not handed to analytics workers or viewers
(`consent_status`); the report lists it so the owning station can renew it.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field

from core_api.db.models import Camera

__all__ = [
    "LIFECYCLE_ATTRIBUTES",
    "MAINTENANCE_STATUSES",
    "OWNERSHIP_VALUES",
    "LifecycleReport",
    "build_lifecycle_report",
    "consent_status",
    "lifecycle_report_csv",
    "validate_lifecycle_attribute",
]

LIFECYCLE_ATTRIBUTES = (
    "installed_on",
    "amc_expires_on",
    "maintenance_status",
    "vendor",
    "model",
    "ownership",
    "consent_ref",
    "consent_expires_on",
)
MAINTENANCE_STATUSES = ("ok", "due", "under_repair", "faulty", "decommissioned")
OWNERSHIP_VALUES = ("government", "private")
_NEEDS_ATTENTION = {"due", "under_repair", "faulty"}
_DATE_ATTRIBUTES = {"installed_on", "amc_expires_on", "consent_expires_on"}
# India has no DST, so a fixed offset is exact and needs no tz database.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def validate_lifecycle_attribute(key: str, value: str) -> str | None:
    """Error message for a bad value, or None. Dates are ISO (YYYY-MM-DD) —
    the one format every department's spreadsheet can export unambiguously."""
    if key in _DATE_ATTRIBUTES:
        try:
            date.fromisoformat(value)
        except ValueError:
            return f"{key} must be a YYYY-MM-DD date, got {value!r}"
    if key == "maintenance_status" and value not in MAINTENANCE_STATUSES:
        return f"maintenance_status must be one of {list(MAINTENANCE_STATUSES)}, got {value!r}"
    if key == "ownership" and value not in OWNERSHIP_VALUES:
        return f"ownership must be one of {list(OWNERSHIP_VALUES)}, got {value!r}"
    return None


def consent_status(
    camera: Camera, *, today: date | None = None, warning_days: int = 60
) -> str | None:
    """None for a government camera; otherwise `valid`, `expiring` or
    `lapsed`. No consent reference or expiry date counts as lapsed: consent
    that cannot be shown does not exist."""
    attrs = camera.attributes or {}
    if attrs.get("ownership") != "private":
        return None
    as_of = today or datetime.now(IST).date()
    expires_on = _date_attr(camera, "consent_expires_on")
    if not attrs.get("consent_ref") or expires_on is None or expires_on < as_of:
        return "lapsed"
    if expires_on <= as_of + timedelta(days=warning_days):
        return "expiring"
    return "valid"


def _date_attr(camera: Camera, key: str) -> date | None:
    raw = (camera.attributes or {}).get(key)
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


class LifecycleCamera(BaseModel):
    camera_id: str
    name: str
    department_name: str | None
    status: str
    installed_on: date | None = None
    age_years: float | None = None
    amc_expires_on: date | None = None
    maintenance_status: str | None = None
    vendor: str | None = None
    model: str | None = None
    findings: list[str] = Field(
        default_factory=list,
        description="ageing | amc_expired | amc_expiring | maintenance | offline "
        "| consent_lapsed | consent_expiring",
    )
    ownership: str | None = None
    consent_ref: str | None = None
    consent_expires_on: date | None = None


class DepartmentLifecycle(BaseModel):
    department_name: str
    total: int = 0
    ageing: int = 0
    amc_expired: int = 0
    amc_expiring: int = 0
    maintenance: int = 0
    offline: int = 0
    consent_lapsed: int = 0
    consent_expiring: int = 0
    install_date_unknown: int = 0


class LifecycleReport(BaseModel):
    as_of: date
    ageing_threshold_years: float
    amc_warning_days: int
    total_cameras: int
    install_date_known: int
    amc_date_known: int
    ageing: int
    amc_expired: int
    amc_expiring: int
    maintenance: int
    offline: int
    private_cameras: int = 0
    consent_lapsed: int = 0
    consent_expiring: int = 0
    by_department: list[DepartmentLifecycle]
    cameras_needing_attention: list[LifecycleCamera]


def build_lifecycle_report(
    cameras: list[Camera],
    *,
    ageing_threshold_years: float = 5.0,
    amc_warning_days: int = 60,
    today: date | None = None,
) -> LifecycleReport:
    # Ages and AMC deadlines are judged on the Gujarat calendar day.
    as_of = today or datetime.now(IST).date()
    warn_until = as_of + timedelta(days=amc_warning_days)
    departments: dict[str, DepartmentLifecycle] = defaultdict(
        lambda: DepartmentLifecycle(department_name="")
    )
    flagged: list[LifecycleCamera] = []
    totals = {
        "ageing": 0,
        "amc_expired": 0,
        "amc_expiring": 0,
        "maintenance": 0,
        "offline": 0,
        "consent_lapsed": 0,
        "consent_expiring": 0,
    }
    install_known = amc_known = private = 0

    for camera in cameras:
        attrs = camera.attributes or {}
        maintenance_status = attrs.get("maintenance_status") or None
        if maintenance_status == "decommissioned":
            continue
        department = camera.department.name if camera.department else "Unassigned"
        row = departments[department]
        row.department_name = department
        row.total += 1

        installed_on = _date_attr(camera, "installed_on")
        amc_expires_on = _date_attr(camera, "amc_expires_on")
        age_years = round((as_of - installed_on).days / 365.25, 1) if installed_on else None
        findings: list[str] = []
        if installed_on is None:
            row.install_date_unknown += 1
        else:
            install_known += 1
            if age_years is not None and age_years >= ageing_threshold_years:
                findings.append("ageing")
        if amc_expires_on is not None:
            amc_known += 1
            if amc_expires_on < as_of:
                findings.append("amc_expired")
            elif amc_expires_on <= warn_until:
                findings.append("amc_expiring")
        if maintenance_status in _NEEDS_ATTENTION:
            findings.append("maintenance")
        if camera.status == "down":
            findings.append("offline")
        consent = consent_status(camera, today=as_of, warning_days=amc_warning_days)
        if consent is not None:
            private += 1
            if consent in ("lapsed", "expiring"):
                findings.append(f"consent_{consent}")

        for finding in findings:
            totals[finding] += 1
            setattr(row, finding, getattr(row, finding) + 1)
        if findings:
            flagged.append(
                LifecycleCamera(
                    camera_id=camera.camera_id,
                    name=camera.name,
                    department_name=camera.department.name if camera.department else None,
                    status=camera.status,
                    installed_on=installed_on,
                    age_years=age_years,
                    amc_expires_on=amc_expires_on,
                    maintenance_status=maintenance_status,
                    vendor=attrs.get("vendor") or None,
                    model=attrs.get("model") or None,
                    findings=findings,
                    ownership=attrs.get("ownership") or None,
                    consent_ref=attrs.get("consent_ref") or None,
                    consent_expires_on=_date_attr(camera, "consent_expires_on"),
                )
            )

    flagged.sort(key=lambda c: (-len(c.findings), -(c.age_years or 0), c.camera_id))
    return LifecycleReport(
        as_of=as_of,
        ageing_threshold_years=ageing_threshold_years,
        amc_warning_days=amc_warning_days,
        total_cameras=sum(d.total for d in departments.values()),
        install_date_known=install_known,
        amc_date_known=amc_known,
        private_cameras=private,
        by_department=sorted(departments.values(), key=lambda d: d.department_name),
        cameras_needing_attention=flagged,
        **totals,
    )


def lifecycle_report_csv(report: LifecycleReport) -> str:
    """One row per camera needing attention — what a department's AMC or
    maintenance cell would actually work through."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "camera_id",
            "name",
            "department",
            "status",
            "installed_on",
            "age_years",
            "amc_expires_on",
            "maintenance_status",
            "vendor",
            "model",
            "ownership",
            "consent_ref",
            "consent_expires_on",
            "findings",
        ]
    )
    for camera in report.cameras_needing_attention:
        writer.writerow(
            [
                camera.camera_id,
                camera.name,
                camera.department_name or "",
                camera.status,
                camera.installed_on.isoformat() if camera.installed_on else "",
                camera.age_years if camera.age_years is not None else "",
                camera.amc_expires_on.isoformat() if camera.amc_expires_on else "",
                camera.maintenance_status or "",
                camera.vendor or "",
                camera.model or "",
                camera.ownership or "",
                camera.consent_ref or "",
                camera.consent_expires_on.isoformat() if camera.consent_expires_on else "",
                ";".join(camera.findings),
            ]
        )
    return buffer.getvalue()
