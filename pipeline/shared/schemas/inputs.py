"""Raw per-sample sequencing inputs (DESIGN.md §2).

Tumour DNA + matched-normal DNA (somatic calling), optional tumour RNA-seq
(expression / mutant-allele transcription), and optional pre-typed HLA alleles
(otherwise typed in Stage 1).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FastqPair(BaseModel):
    """A FASTQ read set for one library. ``r2`` is ``None`` for single-end."""

    model_config = ConfigDict(extra="forbid")

    r1: str
    r2: str | None = None

    @property
    def is_paired(self) -> bool:
        return self.r2 is not None


class SampleInputs(BaseModel):
    """The complete raw input set for one patient/sample."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    tumor_dna: FastqPair
    normal_dna: FastqPair
    tumor_rna: FastqPair | None = None
    hla_alleles: list[str] | None = None
