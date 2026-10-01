"""Durable outbox for detections the API could not take.

Without it a detection posted while the API is unreachable (a WAN cut at a
district site, the API restarting, venue Wi-Fi dropping) is logged and lost,
and with it the sighting that might have been the designated vehicle's only
hop past that camera. Failed posts are kept in a small SQLite file next to
the worker and replayed, oldest first, once the API answers again
(docs/04-SCALE-PLAN.md §2.4: edge autonomy, prioritised drain on reconnect).

Replay is safe to repeat: the API treats a detection it already holds as
accepted (detections/service.py), so a post that timed out after the API had
in fact stored it does not wedge the queue.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

__all__ = ["DetectionOutbox", "QueuedDetection"]

_SCHEMA = """
create table if not exists outbox (
    seq integer primary key autoincrement,
    event_id text not null unique,
    payload text not null,
    has_snapshot integer not null
)
"""


class QueuedDetection:
    __slots__ = ("event_id", "has_snapshot", "payload", "seq")

    def __init__(self, seq: int, event_id: str, payload: dict[str, Any], has_snapshot: bool):
        self.seq = seq
        self.event_id = event_id
        self.payload = payload
        self.has_snapshot = has_snapshot


class DetectionOutbox:
    """Thread-safe: cameras run their pipelines in worker threads, and one
    outbox serves every camera in the process."""

    def __init__(self, path: Path, *, max_rows: int = 200_000) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("pragma journal_mode=wal")
        self._db.execute(_SCHEMA)
        self._max_rows = max_rows

    def put(self, event_id: str, payload: dict[str, Any], *, has_snapshot: bool) -> None:
        with self._lock:
            self._db.execute(
                "insert or ignore into outbox (event_id, payload, has_snapshot) values (?, ?, ?)",
                (event_id, json.dumps(payload), int(has_snapshot)),
            )
            # Bounded: at a busy junction a multi-day outage would otherwise
            # fill the disk. The oldest sightings go first.
            self._db.execute(
                "delete from outbox where seq <= (select max(seq) from outbox) - ?",
                (self._max_rows,),
            )

    def peek(self, limit: int = 50) -> list[QueuedDetection]:
        with self._lock:
            rows = self._db.execute(
                "select seq, event_id, payload, has_snapshot from outbox order by seq limit ?",
                (limit,),
            ).fetchall()
        return [
            QueuedDetection(seq, eid, json.loads(body), bool(snap)) for seq, eid, body, snap in rows
        ]

    def remove(self, event_id: str) -> None:
        with self._lock:
            self._db.execute("delete from outbox where event_id = ?", (event_id,))

    def __len__(self) -> int:
        with self._lock:
            (count,) = self._db.execute("select count(*) from outbox").fetchone()
        return int(count)

    def close(self) -> None:
        with self._lock:
            self._db.close()
