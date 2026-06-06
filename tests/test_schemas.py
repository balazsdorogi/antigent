"""Unit tests for the contract envelope and input schemas."""

import pytest
from pydantic import BaseModel, ValidationError

from pipeline.shared.schemas.base import FileRef, Provenance, StageArtifact
from pipeline.shared.schemas.inputs import FastqPair, SampleInputs


class _Payload(BaseModel):
    value: int
    label: str


def _provenance() -> Provenance:
    return Provenance(
        tool="fastp",
        tool_version="0.24.0",
        image="quay.io/biocontainers/fastp:0.24.0--x",
        image_digest="sha256:deadbeef",
        reference_build="GRCh38.p14",
    )


def _artifact(value: int = 1) -> StageArtifact[_Payload]:
    return StageArtifact[_Payload](
        artifact_type="test.payload",
        sample_id="S1",
        provenance=_provenance(),
        payload=_Payload(value=value, label="x"),
    )


def test_seal_then_verify_roundtrip():
    sealed = _artifact().seal()
    assert sealed.checksum is not None
    assert sealed.verify()


def test_unsealed_artifact_does_not_verify():
    assert not _artifact().verify()


def test_tampering_with_payload_breaks_verification():
    sealed = _artifact(value=1).seal()
    tampered = sealed.model_copy(update={"payload": _Payload(value=999, label="x")})
    assert not tampered.verify()


def test_fileref_from_path(tmp_path):
    p = tmp_path / "reads.txt"
    p.write_bytes(b"ACGT" * 10)
    ref = FileRef.from_path(p)
    assert ref.size_bytes == 40
    assert ref.path == str(p)
    assert len(ref.sha256) == 64


def test_provenance_forbids_unknown_fields():
    # Use model_validate so the intentional extra key is runtime data, not a
    # statically-invalid kwarg (extra="forbid" must reject it at validation time).
    with pytest.raises(ValidationError):
        Provenance.model_validate(
            {
                "tool": "t",
                "tool_version": "1",
                "image": "i",
                "image_digest": "d",
                "reference_build": "GRCh38.p14",
                "bogus": "nope",
            }
        )


def test_sample_inputs_validation():
    s = SampleInputs(
        sample_id="HCC1395",
        tumor_dna=FastqPair(r1="t_1.fq.gz", r2="t_2.fq.gz"),
        normal_dna=FastqPair(r1="n_1.fq.gz", r2="n_2.fq.gz"),
    )
    assert s.tumor_dna.is_paired
    assert s.tumor_rna is None
    assert not FastqPair(r1="se.fq.gz").is_paired
