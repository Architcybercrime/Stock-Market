"""Hash-chained audit log.

Every event references the SHA-256 of the previous event's canonical payload.
Tampering with any historical row breaks the chain; verify_chain() walks the
table and returns the first inconsistent row.

Why hash-chained rather than just append-only:
- Append-only protects against accidental edits but not against an attacker
  with DB access.
- Hash chaining detects retroactive changes even if the attacker has write
  access to the table.

For higher assurance, periodically commit the head hash to an external
witness (a notary service, a second DB, or a public chain). Not implemented
in scaffold.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import orjson

from libs.common.logging import get_logger
from libs.db import AuditLog
from libs.db.session import session_scope

log = get_logger(__name__)


@dataclass
class AuditEvent:
    event_type: str
    actor: str
    payload: dict[str, Any]
    ts: datetime | None = None

    def to_canonical(self) -> bytes:
        """Stable bytes representation used for hashing."""
        ts = (self.ts or datetime.now(UTC)).isoformat()
        # orjson with OPT_SORT_KEYS gives stable ordering for nested dicts
        return orjson.dumps(
            {
                "ts": ts,
                "event_type": self.event_type,
                "actor": self.actor,
                "payload": self.payload,
            },
            option=orjson.OPT_SORT_KEYS,
        )


def canonical_hash(event: AuditEvent, prev_hash: bytes | None) -> bytes:
    h = hashlib.sha256()
    if prev_hash is not None:
        h.update(prev_hash)
    h.update(event.to_canonical())
    return h.digest()


class AuditLogger:
    def __init__(self) -> None:
        self._last_hash: bytes | None = None

    def append(self, event: AuditEvent) -> int:
        """Persist an event. Returns the row id."""
        ts = event.ts or datetime.now(UTC)
        with session_scope() as s:
            last = (
                s.query(AuditLog)
                .order_by(AuditLog.id.desc())
                .limit(1)
                .one_or_none()
            )
            prev_hash = last.row_hash if last else None
            row_hash = canonical_hash(event, prev_hash)
            row = AuditLog(
                ts=ts,
                event_type=event.event_type,
                actor=event.actor,
                payload=event.payload,
                prev_hash=prev_hash,
                row_hash=row_hash,
            )
            s.add(row)
            s.flush()
            self._last_hash = row_hash
            log.info("audit.append", event_type=event.event_type, actor=event.actor, id=row.id)
            return row.id


def verify_chain() -> tuple[bool, int | None]:
    """Walk the audit log and verify the hash chain.

    Returns (ok, first_bad_row_id_if_any).
    """
    from sqlalchemy import select

    prev_hash: bytes | None = None
    with session_scope() as s:
        rows = s.execute(select(AuditLog).order_by(AuditLog.id)).scalars()
        for row in rows:
            event = AuditEvent(
                event_type=row.event_type,
                actor=row.actor,
                payload=row.payload,
                ts=row.ts,
            )
            expected = canonical_hash(event, prev_hash)
            if expected != row.row_hash or row.prev_hash != prev_hash:
                return False, row.id
            prev_hash = row.row_hash
    return True, None
