"""Base contracts: the integrity-bound envelope every inter-stage artifact uses.

``StageArtifact`` is the single handoff type between pipeline stages. It carries the
stage payload, a :class:`Provenance` record, and a SHA-256 ``checksum`` over the
payload's canonical JSON. Stages ``seal()`` an artifact on the way out and the next
stage ``verify()``s it on the way in (DESIGN.md §5). External files referenced
by a payload carry their own :class:`FileRef` SHA-256, giving two-level integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from pipeline.shared.schemas.integrity import payload_checksum, sha256_file


class FileRef(BaseModel):
    """A content-addressed reference to a file on disk or object store."""

    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_path(cls, path: Path | str) -> Self:
        """Build a ``FileRef`` by hashing the file and reading its size."""
        p = Path(path)
        return cls(path=str(p), sha256=sha256_file(p), size_bytes=p.stat().st_size)


class Provenance(BaseModel):
    """Biological-provenance / audit record for one tool invocation (§6.3).

    Captures everything needed to reproduce a step: the exact command, the
    digest-pinned image, the reference build, database releases, and the SHA-256
    of every input and output file.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    tool_version: str
    image: str
    image_digest: str
    reference_build: str
    db_versions: dict[str, str] = Field(default_factory=dict)
    command: list[str] = Field(default_factory=list)
    inputs: list[FileRef] = Field(default_factory=list)
    outputs: list[FileRef] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class StageArtifact[PayloadT: BaseModel](BaseModel):
    """Integrity-bound envelope handed off between stages.

    ``checksum`` is ``None`` until :meth:`seal` binds it to the payload; :meth:`verify`
    recomputes and compares so any later mutation of ``payload`` is detected.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    artifact_type: str
    sample_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    provenance: Provenance
    payload: PayloadT
    checksum: str | None = None

    def compute_checksum(self) -> str:
        """SHA-256 of the payload's canonical JSON (excludes the envelope)."""
        return payload_checksum(self.payload)

    def seal(self) -> Self:
        """Return a copy with ``checksum`` bound to the current payload."""
        return self.model_copy(update={"checksum": self.compute_checksum()})

    def verify(self) -> bool:
        """True iff a checksum is present and matches the current payload."""
        return self.checksum is not None and self.checksum == self.compute_checksum()
