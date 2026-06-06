"""Unit tests for the SHA-256 integrity primitives."""

from pathlib import Path

from pydantic import BaseModel

from pipeline.shared.schemas.integrity import (
    canonical_json,
    payload_checksum,
    sha256_bytes,
    sha256_file,
)

# Well-known SHA-256 test vectors.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


class _KV(BaseModel):
    # Fields intentionally declared out of alphabetical order.
    b: int
    a: int


def test_sha256_bytes_empty():
    assert sha256_bytes(b"") == EMPTY_SHA256


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"abc") == ABC_SHA256


def test_sha256_file_matches_bytes(tmp_path: Path):
    data = b"some genomic-ish bytes\n" * 1000
    p = tmp_path / "x.bin"
    p.write_bytes(data)
    assert sha256_file(p) == sha256_bytes(data)


def test_canonical_json_sorts_keys_and_strips_whitespace():
    assert canonical_json(_KV(b=2, a=1)) == b'{"a":1,"b":2}'


def test_payload_checksum_is_stable():
    assert payload_checksum(_KV(a=1, b=2)) == payload_checksum(_KV(a=1, b=2))


def test_payload_checksum_is_sensitive_to_content():
    assert payload_checksum(_KV(a=1, b=2)) != payload_checksum(_KV(a=1, b=3))
