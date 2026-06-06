"""Tier 2 — cognitive log: the orchestrator's reasoning and decisions.

PLACEHOLDER for the future LLM/orchestration layer (DESIGN.md §6b). No model
runs this round, but the sink and record shape are fixed now so Stage 6 plugs in
without changing the observability contract. Example future entry: "ImmugenX and
BigMHC disagreed on candidate X; included on PRIME + clonality support."
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog

from pipeline.shared.observability._ids import utcnow_iso
from pipeline.shared.storage import RunHandle


class CognitiveLog:
    """Append-only decision-record stream for one run."""

    def __init__(self, handle: RunHandle, *, stream: str = "cognitive.jsonl") -> None:
        self._handle = handle
        self._stream = stream
        self._log = structlog.get_logger("antigent.cognitive")

    def decision(
        self,
        *,
        decision: str,
        rationale: str,
        evidence: Mapping[str, Any] | None = None,
        agent: str | None = None,
    ) -> None:
        """Record a reasoning step: what was decided, why, and on what evidence."""
        record = {
            "ts": utcnow_iso(),
            "tier": "cognitive",
            "agent": agent,
            "decision": decision,
            "rationale": rationale,
            "evidence": dict(evidence or {}),
        }
        self._handle.append_jsonl(self._stream, record)
        self._log.info("decision", decision=decision, agent=agent)
