"""Stage 1 output contracts.

This round models the preprocessing (QC + trim) sub-step. QC metrics are recorded as
*continuous features*, not pass/fail gates (DESIGN.md design principle); any
thresholding lives in later ensemble logic, not here.

The somatic-variant / State A schema is added when the variant-calling container lands.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pipeline.shared.schemas.base import FileRef, StageArtifact

ARTIFACT_TYPE = "stage1.preprocessing"


class Library(StrEnum):
    """The sequencing library a preprocessing run applies to (DESIGN.md §2)."""

    TUMOR_DNA = "tumor_dna"
    NORMAL_DNA = "normal_dna"
    TUMOR_RNA = "tumor_rna"


class FastpQc(BaseModel):
    """Read/base counts and quality rates at one filtering boundary."""

    model_config = ConfigDict(extra="forbid")

    total_reads: int
    total_bases: int
    q20_rate: float
    q30_rate: float


class FastpFiltering(BaseModel):
    """fastp's read-disposition breakdown."""

    model_config = ConfigDict(extra="forbid")

    passed_filter_reads: int
    low_quality_reads: int = 0
    too_many_n_reads: int = 0
    too_short_reads: int = 0
    too_long_reads: int = 0


class FastpMetrics(BaseModel):
    """The QC features extracted from a fastp report."""

    model_config = ConfigDict(extra="forbid")

    before_filtering: FastpQc
    after_filtering: FastpQc
    filtering: FastpFiltering
    duplication_rate: float = 0.0
    adapter_trimmed_reads: int = 0


class PreprocessingResult(BaseModel):
    """Payload for a single library's QC + trimming pass."""

    model_config = ConfigDict(extra="forbid")

    library: Library
    paired_end: bool
    fastp_version: str
    metrics: FastpMetrics
    trimmed: list[FileRef]
    report_json: FileRef
    report_html: FileRef | None = None


PreprocessingArtifact = StageArtifact[PreprocessingResult]
