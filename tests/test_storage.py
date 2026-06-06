"""Unit tests for the pluggable storage seam."""

import json
import stat

import pytest

from pipeline.shared.config import StorageConfig
from pipeline.shared.storage import LocalFsBackend, S3Backend, make_storage


def test_localfs_write_read_roundtrip(tmp_path):
    be = LocalFsBackend(root=tmp_path / "runs")
    be.write_bytes("S1/run1/artifact.json", b'{"x":1}')
    assert be.read_bytes("S1/run1/artifact.json") == b'{"x":1}'


def test_localfs_append_jsonl_is_canonical_and_appends(tmp_path):
    be = LocalFsBackend(root=tmp_path / "runs")
    be.append_jsonl("S1/run1/telemetry.jsonl", {"b": 2, "a": 1})
    be.append_jsonl("S1/run1/telemetry.jsonl", {"event": "done"})
    lines = be.read_bytes("S1/run1/telemetry.jsonl").decode().splitlines()
    assert len(lines) == 2
    assert lines[0] == '{"a":1,"b":2}'  # sorted keys, compact separators
    assert json.loads(lines[1]) == {"event": "done"}


def test_localfs_restrictive_permissions(tmp_path):
    be = LocalFsBackend(root=tmp_path / "runs")
    be.write_bytes("S1/run1/secret.json", b"sensitive")
    f = tmp_path / "runs" / "S1" / "run1" / "secret.json"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "runs").stat().st_mode) == 0o700


def test_open_run_prefixes_keys(tmp_path):
    be = LocalFsBackend(root=tmp_path / "runs")
    run = be.open_run("HCC1395", "20260606T000000Z")
    run.append_jsonl("audit.jsonl", {"tool": "fastp"})
    p = tmp_path / "runs" / "HCC1395" / "20260606T000000Z" / "audit.jsonl"
    assert json.loads(p.read_text()) == {"tool": "fastp"}
    assert run.uri("audit.jsonl").startswith("file://")


def test_s3_backend_data_ops_raise_not_implemented():
    be = S3Backend(bucket="b", prefix="antigent", kms_key_id=None)
    with pytest.raises(NotImplementedError):
        be.write_bytes("k", b"x")
    with pytest.raises(NotImplementedError):
        be.read_bytes("k")
    # location() is safe to compute without an implementation.
    assert be.location("S1/run1/audit.jsonl") == "s3://b/antigent/S1/run1/audit.jsonl"


def test_make_storage_defaults_to_local(tmp_path):
    be = make_storage(StorageConfig(backend="local", root=tmp_path))
    assert isinstance(be, LocalFsBackend)


def test_make_storage_s3_requires_bucket():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        make_storage(StorageConfig(backend="s3", s3_bucket=None))


def test_make_storage_rejects_unknown_backend():
    with pytest.raises(ValueError, match="unknown storage backend"):
        make_storage(StorageConfig(backend="nope"))
