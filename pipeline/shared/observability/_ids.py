"""Small time / run-id helpers shared by the observability sinks."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (sink record timestamps)."""
    return datetime.now(tz=UTC).isoformat()


def new_run_id() -> str:
    """A sortable, collision-resistant run id: ``YYYYmmddTHHMMSSZ-<6hex>``."""
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"
