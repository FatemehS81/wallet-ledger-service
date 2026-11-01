"""Canonical request fingerprint.

The fingerprint is the SHA-256 of a canonical JSON document containing only
``type`` and ``amount``. ``description`` is deliberately excluded: a retry that
changes only the note must replay the original result instead of conflicting.
"""

import hashlib
import json


def make_fingerprint(entry_type: str, amount: int) -> str:
    """Return a deterministic SHA-256 hex digest for an operation."""
    payload = json.dumps(
        {"type": entry_type, "amount": amount},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
