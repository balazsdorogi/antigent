"""Unit tests for the container runner (subprocess mocked; no Docker required)."""

import json
import subprocess

import pytest

from pipeline.shared.containers import (
    ContainerImage,
    ContainerRunError,
    Mount,
    run_container,
)
from pipeline.shared.observability import RunContext
from pipeline.shared.schemas.integrity import sha256_file
from pipeline.shared.storage import LocalFsBackend

IMAGE = ContainerImage(
    name="fastp",
    repository="quay.io/biocontainers/fastp",
    tag="0.24.1--heae3180_0",
    tool_version="0.24.1",
    digest="sha256:abc",
)


def _fake_docker(*, run_rc=0, run_stderr="", on_run=None):
    """A fake subprocess.run answering `docker run` and `docker image inspect`."""

    def fake_run(cmd, **kwargs):
        if "inspect" in cmd:
            resolved = f"{IMAGE.repository}@sha256:RESOLVED\n"
            return subprocess.CompletedProcess(cmd, 0, resolved, "")
        if on_run is not None:
            on_run()
        return subprocess.CompletedProcess(cmd, run_rc, "stdout", run_stderr)

    return fake_run


def _patch(monkeypatch, fake):
    monkeypatch.setattr("pipeline.shared.containers.subprocess.run", fake)


def _ctx(tmp_path):
    return RunContext.open("S1", backend=LocalFsBackend(root=tmp_path / "runs"), run_id="r1")


def _audit(tmp_path):
    p = tmp_path / "runs" / "S1" / "r1" / "audit.jsonl"
    return json.loads(p.read_text().splitlines()[0])


def test_command_is_pinned_and_amd64(tmp_path, monkeypatch):
    _patch(monkeypatch, _fake_docker())
    res = run_container(IMAGE, ["--version"], run_ctx=_ctx(tmp_path), stage="stage1")
    assert res.command[:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert "quay.io/biocontainers/fastp@sha256:abc" in res.command
    assert res.command[-1] == "--version"


def test_provenance_records_exact_command_and_resolved_digest(tmp_path, monkeypatch):
    _patch(monkeypatch, _fake_docker())
    res = run_container(IMAGE, ["--version"], run_ctx=_ctx(tmp_path), stage="stage1.preprocessing")
    audit = _audit(tmp_path)
    assert audit["command"] == res.command
    assert audit["image"] == "quay.io/biocontainers/fastp@sha256:abc"
    assert audit["image_digest"] == "sha256:RESOLVED"
    assert audit["reference_build"] == "GRCh38.p14"
    assert audit["stage"] == "stage1.preprocessing"


def test_mounts_and_workdir_rendered(tmp_path, monkeypatch):
    _patch(monkeypatch, _fake_docker())
    res = run_container(
        IMAGE,
        ["x"],
        run_ctx=_ctx(tmp_path),
        mounts=[Mount(tmp_path, "/data", read_only=True)],
        workdir="/data",
    )
    cmd = res.command
    assert cmd[cmd.index("-w") + 1] == "/data"
    assert cmd[cmd.index("-v") + 1].endswith(":/data:ro")


def test_nonzero_exit_raises_but_records_provenance(tmp_path, monkeypatch):
    _patch(monkeypatch, _fake_docker(run_rc=2, run_stderr="boom"))
    with pytest.raises(ContainerRunError, match="exited 2"):
        run_container(IMAGE, ["x"], run_ctx=_ctx(tmp_path))
    assert _audit(tmp_path)["command"][0] == "docker"  # provenance written before raise


def test_inputs_and_outputs_are_hashed_into_provenance(tmp_path, monkeypatch):
    inp = tmp_path / "in.fq"
    inp.write_bytes(b"@r\nACGT\n+\nIIII\n")
    out = tmp_path / "out.fq"
    _patch(monkeypatch, _fake_docker(on_run=lambda: out.write_bytes(b"trimmed")))
    res = run_container(IMAGE, ["x"], run_ctx=_ctx(tmp_path), inputs=[inp], outputs=[out])
    prov = res.provenance
    assert prov.inputs[0].sha256 == sha256_file(inp)
    assert prov.inputs[0].path == str(inp)
    assert prov.outputs[0].sha256 == sha256_file(out)


def test_image_ref_prefers_digest_then_tag():
    assert IMAGE.ref == "quay.io/biocontainers/fastp@sha256:abc"
    assert IMAGE.is_pinned
    unpinned = ContainerImage(name="t", repository="repo", tag="1.0", tool_version="1.0")
    assert unpinned.ref == "repo:1.0"
    assert not unpinned.is_pinned
