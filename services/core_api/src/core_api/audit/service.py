"""M12's hash-chained audit trail — docs/01-ARCHITECTURE.md §7: "audit_log
rows carry prev_hash/row_hash — an append-only hash chain, verifiable by a
CLI command." See scripts/verify_audit_log.py for the verification CLI and
docs/08-SECURITY-HARDENING.md for the full design writeup.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import AuditLogEntry

__all__ = ["ChainVerificationResult", "record_audit_event", "verify_chain"]

# A fixed, documented genesis value — not a real hash of anything, just a
# distinguishable "there is no previous row" marker the same length as a
# real SHA-256 hex digest.
GENESIS_HASH = "0" * 64

# Any fixed integer works as a Postgres advisory-lock key — this one has no
# meaning beyond "the audit log append lock," picked once and never reused
# elsewhere in this codebase.
_APPEND_LOCK_KEY = 891_247_003


def _canonical_payload(entry: AuditLogEntry) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace, so the
    same logical row always serializes to the exact same bytes regardless
    of dict insertion order or an ORM refresh."""
    payload = {
        "id": str(entry.id),
        "actor_email": entry.actor_email,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "detail": entry.detail,
        "created_at": entry.created_at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_row_hash(entry: AuditLogEntry, *, prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + _canonical_payload(entry)).encode()).hexdigest()


async def _last_entry(session: AsyncSession) -> AuditLogEntry | None:
    result = await session.execute(
        select(AuditLogEntry).order_by(AuditLogEntry.seq.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def record_audit_event(
    session: AsyncSession,
    *,
    actor_email: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, object] | None = None,
) -> AuditLogEntry:
    """Appends one row to the hash chain. Holds a Postgres transaction-scoped
    advisory lock (released automatically at COMMIT/ROLLBACK) around the
    read-prev-hash-then-insert sequence — without it, two concurrent
    callers could both read the same "last row" and each compute a
    row_hash chained from the same prev_hash, silently forking the chain
    instead of extending it."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _APPEND_LOCK_KEY})

    last = await _last_entry(session)
    prev_hash = last.row_hash if last is not None else GENESIS_HASH

    entry = AuditLogEntry(
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
        prev_hash=prev_hash,
        row_hash="",  # placeholder — computed below, once id/created_at are assigned
    )
    session.add(entry)
    # A flush (not a full commit) assigns the ORM-level `default=` values
    # for id/created_at — they're genuinely None on the Python object until
    # this point, not eagerly computed at __init__ time. Hashing before
    # this flush would silently hash the placeholder None values instead
    # of the real ones.
    await session.flush()
    entry.row_hash = _compute_row_hash(entry, prev_hash=prev_hash)
    await session.flush()
    return entry


@dataclass(frozen=True, slots=True)
class ChainVerificationResult:
    intact: bool
    rows_checked: int
    first_broken_seq: int | None = None
    detail: str | None = None
    checked_actions: list[str] = field(default_factory=list)


async def verify_chain(session: AsyncSession) -> ChainVerificationResult:
    """Walks every row in insertion order, recomputing each row's hash from
    its own stored fields and the *previous row's stored row_hash* — if
    anyone ever edited a row in place (changed a reason, deleted an entry
    and renumbered, anything), the recomputed hash stops matching from that
    point on, and every row after it is flagged too (a hash chain's whole
    point: tampering anywhere breaks everything downstream of it)."""
    result = await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.seq.asc()))
    rows = list(result.scalars().all())

    expected_prev = GENESIS_HASH
    checked_actions: list[str] = []
    for row in rows:
        if row.prev_hash != expected_prev:
            return ChainVerificationResult(
                intact=False,
                rows_checked=len(checked_actions),
                first_broken_seq=row.seq,
                detail=f"row {row.seq}'s prev_hash does not match the prior row's row_hash.",
                checked_actions=checked_actions,
            )
        recomputed = _compute_row_hash(row, prev_hash=row.prev_hash)
        if recomputed != row.row_hash:
            return ChainVerificationResult(
                intact=False,
                rows_checked=len(checked_actions),
                first_broken_seq=row.seq,
                detail=f"row {row.seq}'s stored row_hash does not match its recomputed hash "
                "— its content was modified after being written.",
                checked_actions=checked_actions,
            )
        checked_actions.append(row.action)
        expected_prev = row.row_hash

    return ChainVerificationResult(
        intact=True, rows_checked=len(rows), checked_actions=checked_actions
    )
