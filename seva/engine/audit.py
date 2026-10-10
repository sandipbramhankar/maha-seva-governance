"""
Audit chain
============
  Fig 9   Every decision is recorded, hash-linked and reproducible.

Each entry carries the inputs, the scores, the weights and thresholds in force,
the agent votes, the officer who acted, and the SHA-256 of the previous entry.
Changing any earlier entry breaks every hash after it, so a record cannot be
quietly rewritten once the next decision is taken.

The chaining primitive comes from indicer's quorum module, which is where the
scheme is specified.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

GENESIS = "0" * 64


@dataclass
class AuditEntry:
    seva_id:       str
    sequence:      int
    timestamp:     str
    event:         str              # "verified" | "forwarded" | "approved" | ...
    actor_id:      str
    actor_name:    str
    payload:       Dict[str, Any] = field(default_factory=dict)
    previous_hash: str = GENESIS
    entry_hash:    str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _hash(previous_hash: str, body: Dict[str, Any]) -> str:
    """SHA-256 over the previous hash concatenated with the canonical body."""
    canonical = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()


class AuditChain:
    """Append-only chain of decision records for one Seva ticket."""

    def __init__(self, seva_id: str) -> None:
        self.seva_id = seva_id
        self.entries: List[AuditEntry] = []

    @property
    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else GENESIS

    def append(self, event: str, actor_id: str, actor_name: str,
               payload: Optional[Dict[str, Any]] = None) -> AuditEntry:
        body = {
            "seva_id":   self.seva_id,
            "sequence":  len(self.entries) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event":     event,
            "actor_id":  actor_id,
            "actor_name": actor_name,
            "payload":   payload or {},
        }
        entry = AuditEntry(
            **body,
            previous_hash=self.head,
            entry_hash=_hash(self.head, body),
        )
        self.entries.append(entry)
        return entry

    def verify(self) -> tuple[bool, Optional[str]]:
        """
        Recompute every hash. Returns (ok, first_broken_link).

        An auditor runs this to prove no entry was altered after the fact.
        """
        previous = GENESIS
        for entry in self.entries:
            body = {
                "seva_id":   entry.seva_id,
                "sequence":  entry.sequence,
                "timestamp": entry.timestamp,
                "event":     entry.event,
                "actor_id":  entry.actor_id,
                "actor_name": entry.actor_name,
                "payload":   entry.payload,
            }
            if entry.previous_hash != previous:
                return False, f"entry {entry.sequence}: previous hash does not match"
            if _hash(previous, body) != entry.entry_hash:
                return False, f"entry {entry.sequence}: contents were altered"
            previous = entry.entry_hash
        return True, None

    def as_list(self) -> List[Dict[str, Any]]:
        return [e.as_dict() for e in self.entries]
