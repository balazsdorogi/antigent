"""Tier 3 — biological provenance / audit (DESIGN.md §6.3).

The reproducibility record: for every tool invocation, the exact command and flags,
the digest-pinned image, reference build, database releases, and the SHA-256 of every
input and output file. Append-only; this is the auditable source of truth.
"""

from __future__ import annotations

import structlog

from pipeline.shared.observability._ids import utcnow_iso
from pipeline.shared.schemas.base import Provenance
from pipeline.shared.storage import RunHandle


class ProvenanceLog:
    """Append-only audit stream for one run."""

    def __init__(self, handle: RunHandle, *, stream: str = "audit.jsonl") -> None:
        self._handle = handle
        self._stream = stream
        self._log = structlog.get_logger("antigent.audit")

    def record(self, provenance: Provenance, *, stage: str | None = None) -> None:
        """Append one provenance record to the audit log."""
        entry = {"ts": utcnow_iso(), "tier": "audit", "stage": stage}
        entry.update(provenance.model_dump(mode="json"))
        self._handle.append_jsonl(self._stream, entry)
        self._log.info(
            "provenance",
            tool=provenance.tool,
            image_digest=provenance.image_digest,
            stage=stage,
        )
