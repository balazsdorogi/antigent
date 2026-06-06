"""Unit tests for the three-tier observability sinks + RunContext."""

import json

import pytest
from pydantic import BaseModel

from pipeline.shared.observability import RunContext
from pipeline.shared.schemas.base import Provenance, StageArtifact
from pipeline.shared.storage import LocalFsBackend


class _P(BaseModel):
    value: int


def _ctx(tmp_path):
    backend = LocalFsBackend(root=tmp_path / "runs")
    return RunContext.open("S1", backend=backend, run_id="run1")


def _read(tmp_path, name):
    p = tmp_path / "runs" / "S1" / "run1" / name
    return [json.loads(line) for line in p.read_text().splitlines()]


def _prov() -> Provenance:
    return Provenance(
        tool="fastp",
        tool_version="0.24.0",
        image="img",
        image_digest="sha256:abc",
        reference_build="GRCh38.p14",
    )


def test_tool_run_emits_start_and_end(tmp_path):
    ctx = _ctx(tmp_path)
    with ctx.telemetry.tool_run("fastp", image="img@sha256:x") as m:
        m.exit_code = 0
    records = _read(tmp_path, "telemetry.jsonl")
    assert [r["event"] for r in records] == ["tool_start", "tool_end"]
    assert records[-1]["exit_code"] == 0
    assert "duration_s" in records[-1]


def test_tool_run_records_error_then_reraises(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(RuntimeError):  # noqa: SIM117 (context nesting is the point)
        with ctx.telemetry.tool_run("fastp", image="img"):
            raise RuntimeError("boom")
    events = [r["event"] for r in _read(tmp_path, "telemetry.jsonl")]
    assert "tool_error" in events
    assert events[-1] == "tool_end"


def test_cognitive_decision_logged(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.cognitive.decision(
        decision="include candidate X",
        rationale="PRIME + clonality support",
        agent="supervisor",
    )
    rec = _read(tmp_path, "cognitive.jsonl")[0]
    assert rec["decision"] == "include candidate X"
    assert rec["agent"] == "supervisor"


def test_provenance_record_logged(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.provenance.record(_prov(), stage="stage1.preprocessing")
    rec = _read(tmp_path, "audit.jsonl")[0]
    assert rec["tool"] == "fastp"
    assert rec["image_digest"] == "sha256:abc"
    assert rec["stage"] == "stage1.preprocessing"


def test_write_artifact_requires_sealed(tmp_path):
    ctx = _ctx(tmp_path)
    art = StageArtifact[_P](
        artifact_type="test.p", sample_id="S1", provenance=_prov(), payload=_P(value=1)
    )
    with pytest.raises(ValueError, match="sealed"):
        ctx.write_artifact(art)


def test_write_artifact_persists_and_verifies(tmp_path):
    ctx = _ctx(tmp_path)
    art = StageArtifact[_P](
        artifact_type="test.p", sample_id="S1", provenance=_prov(), payload=_P(value=1)
    ).seal()
    uri = ctx.write_artifact(art)
    assert uri.startswith("file://")
    p = tmp_path / "runs" / "S1" / "run1" / "artifacts" / "test.p.json"
    loaded = StageArtifact[_P].model_validate_json(p.read_text())
    assert loaded.verify()
