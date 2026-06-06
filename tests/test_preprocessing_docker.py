"""End-to-end fastp integration test (requires a running Docker daemon).

Exercises the whole platform spine on one real tool: pull (on demand) -> digest-pinned
run -> telemetry + provenance -> parse -> schema -> checksum-seal -> persist.

Run with ``make test-docker`` (or ``pytest -m docker``). Skipped automatically when
the Docker daemon is unavailable, so the default ``make test`` run is never blocked.
"""

import stat
import subprocess
from pathlib import Path

import pytest

from pipeline.neoantigen_discovery.preprocessing import run_fastp
from pipeline.shared.observability import RunContext
from pipeline.shared.schemas.inputs import FastqPair
from pipeline.shared.schemas.integrity import sha256_file
from pipeline.shared.schemas.stage1 import Library, PreprocessingArtifact
from pipeline.shared.storage import LocalFsBackend


def _docker_ready() -> bool:
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


requires_docker = pytest.mark.skipif(not _docker_ready(), reason="Docker daemon not available")


@pytest.mark.docker
@requires_docker
def test_fastp_end_to_end(tmp_path, synthetic_fastq_pair):
    r1, r2 = synthetic_fastq_pair
    backend = LocalFsBackend(root=tmp_path / "runs")
    ctx = RunContext.open("DEMO", backend=backend, run_id="itest")

    artifact = run_fastp(
        Library.TUMOR_DNA,
        FastqPair(r1=str(r1), r2=str(r2)),
        run_ctx=ctx,
        work_dir=tmp_path / "work",
    )

    # Contract + integrity binding.
    assert artifact.verify()
    assert artifact.artifact_type == "stage1.preprocessing"
    assert artifact.payload.paired_end
    assert len(artifact.payload.trimmed) == 2

    # Each trimmed FileRef's sha256 matches the file actually on disk.
    for ref in artifact.payload.trimmed:
        p = Path(ref.path)
        assert p.exists()
        assert sha256_file(p) == ref.sha256

    # QC metrics were parsed out of fastp's report.
    metrics = artifact.payload.metrics
    assert metrics.before_filtering.total_reads >= 200
    assert metrics.after_filtering.total_reads <= metrics.before_filtering.total_reads
    assert metrics.filtering.passed_filter_reads >= 1
    assert 0.0 <= metrics.before_filtering.q30_rate <= 1.0

    # Provenance: exact pinned command, resolved digest, reference build, file refs.
    prov = artifact.provenance
    assert prov.tool == "fastp"
    assert prov.command[:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert prov.image.startswith("quay.io/biocontainers/fastp@sha256:")
    assert prov.image_digest.startswith("sha256:")
    assert prov.reference_build == "GRCh38.p14"
    assert len(prov.inputs) == 2
    assert len(prov.outputs) >= 3

    # Logs + artifact persisted via LocalFsBackend with restrictive perms.
    run_dir = tmp_path / "runs" / "DEMO" / "itest"
    audit = run_dir / "audit.jsonl"
    telemetry = run_dir / "telemetry.jsonl"
    assert audit.exists() and telemetry.exists()
    assert stat.S_IMODE(audit.stat().st_mode) == 0o600

    artifact_file = run_dir / "artifacts" / "stage1.preprocessing.tumor_dna.json"
    assert artifact_file.exists()
    assert stat.S_IMODE(artifact_file.stat().st_mode) == 0o600
    assert PreprocessingArtifact.model_validate_json(artifact_file.read_text()).verify()
