"""Ageing-infrastructure and maintenance gap analysis (Model 1)."""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.registry.bulk_import import parse_and_import_csv
from core_api.registry.lifecycle import (
    build_lifecycle_report,
    lifecycle_report_csv,
    validate_lifecycle_attribute,
)
from core_api.registry.service import get_camera, list_cameras

TODAY = date(2026, 10, 12)
CSV = """camera_id,name,department_name,installed_on,amc_expires_on,maintenance_status,vendor
lc-old,Old junction,Police,2018-03-01,2027-01-01,ok,Hikvision
lc-amc,Depot gate,GSRTC,2024-06-01,2026-09-30,,Dahua
lc-soon,PHC entrance,Health,2025-01-01,2026-11-15,,
lc-repair,Market,Municipal,,,under_repair,
lc-fine,New junction,Police,2025-08-01,2028-01-01,ok,
lc-gone,Retired pole,Police,2012-01-01,,decommissioned,
"""


async def _import(session: AsyncSession, body: str = CSV) -> None:
    result = await parse_and_import_csv(session, body, dry_run=False)
    assert result.failed == 0, result.rows


async def test_csv_lifecycle_columns_land_in_camera_attributes(db_session: AsyncSession) -> None:
    await _import(db_session)

    camera = await get_camera(db_session, "lc-old")

    assert camera is not None
    assert camera.attributes == {
        "installed_on": "2018-03-01",
        "amc_expires_on": "2027-01-01",
        "maintenance_status": "ok",
        "vendor": "Hikvision",
    }


async def test_a_bad_lifecycle_value_rejects_only_its_row(db_session: AsyncSession) -> None:
    body = (
        "camera_id,name,installed_on,maintenance_status\n"
        "lc-a,A,01/02/2019,ok\n"
        "lc-b,B,2019-02-01,broken\n"
        "lc-c,C,2019-02-01,faulty\n"
    )

    result = await parse_and_import_csv(db_session, body, dry_run=True)

    assert [r.ok for r in result.rows] == [False, False, True]
    assert "YYYY-MM-DD" in (result.rows[0].error or "")
    assert "maintenance_status" in (result.rows[1].error or "")


async def test_report_flags_ageing_amc_and_maintenance_by_department(
    db_session: AsyncSession,
) -> None:
    await _import(db_session)
    cameras = [c for c in await list_cameras(db_session) if c.camera_id.startswith("lc-")]

    report = build_lifecycle_report(
        cameras, ageing_threshold_years=5, amc_warning_days=60, today=TODAY
    )

    # Decommissioned cameras are out of the estate, not a finding.
    assert report.total_cameras == 5
    assert (report.ageing, report.amc_expired, report.amc_expiring, report.maintenance) == (
        1,
        1,
        1,
        1,
    )
    assert report.install_date_known == 4
    findings = {c.camera_id: c.findings for c in report.cameras_needing_attention}
    assert findings == {
        "lc-old": ["ageing"],
        "lc-amc": ["amc_expired"],
        "lc-soon": ["amc_expiring"],
        "lc-repair": ["maintenance"],
    }
    old = next(c for c in report.cameras_needing_attention if c.camera_id == "lc-old")
    assert old.age_years == 8.6
    police = next(d for d in report.by_department if d.department_name == "Police")
    assert (police.total, police.ageing) == (2, 1)
    municipal = next(d for d in report.by_department if d.department_name == "Municipal")
    assert municipal.install_date_unknown == 1


async def test_offline_cameras_are_a_maintenance_signal(db_session: AsyncSession) -> None:
    await _import(db_session)
    camera = await get_camera(db_session, "lc-fine")
    assert camera is not None
    camera.status = "down"

    report = build_lifecycle_report([camera], today=TODAY)

    assert report.offline == 1
    assert report.cameras_needing_attention[0].findings == ["offline"]


async def test_csv_export_is_a_work_list(db_session: AsyncSession) -> None:
    await _import(db_session)
    cameras = [c for c in await list_cameras(db_session) if c.camera_id.startswith("lc-")]

    rows = list(
        csv.DictReader(
            io.StringIO(lifecycle_report_csv(build_lifecycle_report(cameras, today=TODAY)))
        )
    )

    assert {r["camera_id"] for r in rows} == {"lc-old", "lc-amc", "lc-soon", "lc-repair"}
    assert next(r for r in rows if r["camera_id"] == "lc-old")["vendor"] == "Hikvision"


def test_validation_messages() -> None:
    assert validate_lifecycle_attribute("installed_on", "2020-01-01") is None
    assert validate_lifecycle_attribute("vendor", "anything") is None
    assert validate_lifecycle_attribute("amc_expires_on", "soon") is not None
    assert validate_lifecycle_attribute("maintenance_status", "decommissioned") is None
