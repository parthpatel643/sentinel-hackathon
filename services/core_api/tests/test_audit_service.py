"""Tests for the hash-chained audit log — real Postgres (see conftest.py's
transaction-rollback isolation), covering append correctness, the genesis
row, and tamper detection (the whole point of a hash chain)."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import GENESIS_HASH, record_audit_event, verify_chain
from core_api.db.models import AuditLogEntry


async def test_the_first_row_chains_from_the_genesis_hash(db_session: AsyncSession) -> None:
    entry = await record_audit_event(
        db_session,
        actor_email="admin@sentinel-platform.com",
        action="test_action",
        resource_type="test",
        resource_id="res-1",
    )

    assert entry.prev_hash == GENESIS_HASH
    assert entry.row_hash != GENESIS_HASH
    assert len(entry.row_hash) == 64  # a real sha256 hex digest


async def test_a_second_row_chains_from_the_first_rows_hash(db_session: AsyncSession) -> None:
    first = await record_audit_event(
        db_session, actor_email="a@example.com", action="first", resource_type="test"
    )
    second = await record_audit_event(
        db_session, actor_email="b@example.com", action="second", resource_type="test"
    )

    assert second.prev_hash == first.row_hash
    assert second.row_hash != first.row_hash


async def test_verify_chain_is_intact_after_several_untouched_appends(
    db_session: AsyncSession,
) -> None:
    for i in range(5):
        await record_audit_event(
            db_session, actor_email="admin@example.com", action=f"action-{i}", resource_type="test"
        )

    result = await verify_chain(db_session)

    assert result.intact is True
    assert result.rows_checked == 5
    assert result.first_broken_seq is None


async def test_verify_chain_detects_a_tampered_detail_field(db_session: AsyncSession) -> None:
    """The entire point of the hash chain: editing a row in place after the
    fact must be detectable, not silently accepted."""
    await record_audit_event(
        db_session,
        actor_email="admin@example.com",
        action="reveal",
        resource_type="detection",
        detail={"reason": "original legitimate reason"},
    )
    tampered = await record_audit_event(
        db_session, actor_email="admin@example.com", action="second", resource_type="test"
    )

    # Simulate someone editing history directly in the database — exactly
    # what the hash chain exists to catch.
    await db_session.execute(
        update(AuditLogEntry)
        .where(AuditLogEntry.action == "reveal")
        .values(detail={"reason": "tampered reason"})
    )
    await db_session.flush()

    result = await verify_chain(db_session)

    assert result.intact is False
    assert result.first_broken_seq is not None
    # The tampered row breaks first, but the chain is walked in seq order —
    # confirm the break is reported at or before the later row.
    assert result.first_broken_seq <= tampered.seq


async def test_verify_chain_on_an_empty_log_is_trivially_intact(db_session: AsyncSession) -> None:
    result = await verify_chain(db_session)

    assert result.intact is True
    assert result.rows_checked == 0


async def test_concurrent_appends_never_produce_duplicate_row_hashes(
    db_session: AsyncSession,
) -> None:
    """Not a true multi-connection concurrency test (db_session is one
    connection), but proves the advisory-lock-guarded read-then-insert
    sequence produces a correctly linked chain even for back-to-back calls
    with identical actor/action/resource_type (the fields alone wouldn't
    be enough to distinguish rows without prev_hash chaining them)."""
    entries = [
        await record_audit_event(
            db_session, actor_email="same@example.com", action="same_action", resource_type="test"
        )
        for _ in range(3)
    ]

    row_hashes = {e.row_hash for e in entries}
    assert len(row_hashes) == 3  # no collisions
    assert entries[1].prev_hash == entries[0].row_hash
    assert entries[2].prev_hash == entries[1].row_hash
