"""SHA-256 integrity primitives for the inter-stage contract layer.

Two-level binding (DESIGN.md §5):

- file-level: :func:`sha256_file` hashes each external artifact (FASTQ/BAM/VCF/...),
  recorded inside :class:`~pipeline.shared.schemas.base.FileRef`;
- payload-level: :func:`payload_checksum` hashes the *canonical* JSON of a Pydantic
  payload so a ``StageArtifact`` can be sealed and later verified byte-for-byte.

Canonical JSON (sorted keys, no whitespace) makes the checksum independent of field
declaration order or dict ordering, so the same data always yields the same hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

_CHUNK = 1 << 20  # 1 MiB — stream large genomic files in constant memory.


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = _CHUNK) -> str:
    """Return the hex SHA-256 of a file, read in chunks (constant memory)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: BaseModel) -> bytes:
    """Serialise a model to canonical JSON bytes: sorted keys, no whitespace.

    Deterministic, so the same payload always hashes to the same checksum.
    """
    data = payload.model_dump(mode="json")
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def payload_checksum(payload: BaseModel) -> str:
    """SHA-256 of a payload's canonical JSON — the in-band integrity binding."""
    return sha256_bytes(canonical_json(payload))
