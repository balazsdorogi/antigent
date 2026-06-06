"""Pydantic contracts bound with SHA-256 integrity (DESIGN.md §5)."""

from pipeline.shared.schemas.base import FileRef, Provenance, StageArtifact
from pipeline.shared.schemas.inputs import FastqPair, SampleInputs
from pipeline.shared.schemas.integrity import (
    canonical_json,
    payload_checksum,
    sha256_bytes,
    sha256_file,
)
from pipeline.shared.schemas.stage1 import (
    Library,
    PreprocessingArtifact,
    PreprocessingResult,
)

__all__ = [
    "FastqPair",
    "FileRef",
    "Library",
    "PreprocessingArtifact",
    "PreprocessingResult",
    "Provenance",
    "SampleInputs",
    "StageArtifact",
    "canonical_json",
    "payload_checksum",
    "sha256_bytes",
    "sha256_file",
]
