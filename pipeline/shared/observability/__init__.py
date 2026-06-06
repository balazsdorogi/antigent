"""Three-tier observability: system telemetry, cognitive log, biological provenance.

A :class:`RunContext` opens one run through the storage backend and bundles the three
sinks. Everything is persisted as JSONL via the backend, so destination + at-rest
encryption are a config swap (local now, encrypted S3 on AWS).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import structlog

from pipeline.shared.observability._ids import new_run_id
from pipeline.shared.observability.cognitive import CognitiveLog
from pipeline.shared.observability.provenance import ProvenanceLog
from pipeline.shared.observability.telemetry import TelemetrySink, ToolRunMetrics
from pipeline.shared.schemas.base import StageArtifact
from pipeline.shared.storage import RunHandle, StorageBackend, make_storage

_CONFIGURED = False


def configure_logging() -> None:
    """Configure structlog for human-readable console output (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        # Logs to stderr so stdout stays clean for program output (e.g. artifact JSON).
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


@dataclass
class RunContext:
    """One run's observability surface: the three sinks + artifact persistence."""

    sample_id: str
    run_id: str
    handle: RunHandle
    telemetry: TelemetrySink
    cognitive: CognitiveLog
    provenance: ProvenanceLog

    @classmethod
    def open(
        cls,
        sample_id: str,
        *,
        backend: StorageBackend | None = None,
        run_id: str | None = None,
    ) -> RunContext:
        """Open a run (default storage backend + generated run id)."""
        configure_logging()
        backend = backend or make_storage()
        run_id = run_id or new_run_id()
        handle = backend.open_run(sample_id, run_id)
        return cls(
            sample_id=sample_id,
            run_id=run_id,
            handle=handle,
            telemetry=TelemetrySink(handle),
            cognitive=CognitiveLog(handle),
            provenance=ProvenanceLog(handle),
        )

    def write_artifact(self, artifact: StageArtifact[Any], *, name: str | None = None) -> str:
        """Persist a *sealed* artifact as JSON; return its storage URI."""
        if artifact.checksum is None:
            raise ValueError("artifact must be sealed (call .seal()) before it is persisted")
        key = f"artifacts/{name or artifact.artifact_type + '.json'}"
        self.handle.write_bytes(key, artifact.model_dump_json(indent=2).encode("utf-8"))
        uri = self.handle.uri(key)
        self.telemetry.event(
            "artifact_written",
            artifact_type=artifact.artifact_type,
            key=key,
            checksum=artifact.checksum,
            uri=uri,
        )
        return uri


__all__ = [
    "CognitiveLog",
    "ProvenanceLog",
    "RunContext",
    "TelemetrySink",
    "ToolRunMetrics",
    "configure_logging",
]
