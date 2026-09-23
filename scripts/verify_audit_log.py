#!/usr/bin/env python3
"""Verifies the hash-chained audit log's integrity end-to-end —
docs/01-ARCHITECTURE.md §7: "an append-only hash chain, verifiable by a
CLI command." Walks every row in insertion order, recomputing each row's
hash from its own stored fields and the previous row's stored hash; any
row edited in place after being written will make its recomputed hash
stop matching, and this is reported immediately with the exact row.

Usage:
    uv run --package core_api python scripts/verify_audit_log.py
"""

from __future__ import annotations

import asyncio
import sys

from core_api.audit.service import verify_chain
from core_api.db.base import get_sessionmaker


async def main() -> int:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await verify_chain(session)

    if result.rows_checked == 0 and result.intact:
        print("Audit log is empty — nothing to verify yet.")
        return 0

    if result.intact:
        print(f"OK: audit log chain intact — {result.rows_checked} row(s) verified.")
        actions_summary = ", ".join(sorted(set(result.checked_actions)))
        print(f"Actions seen: {actions_summary}")
        return 0

    print("FAILED: audit log chain is broken.")
    print(f"  First broken row: seq={result.first_broken_seq}")
    print(f"  Detail: {result.detail}")
    print(f"  Rows verified before the break: {result.rows_checked}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
