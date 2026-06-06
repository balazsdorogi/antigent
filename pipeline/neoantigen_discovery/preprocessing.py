"""Stage 1 — preprocessing: QC + adapter/quality trimming with fastp.

fastp is the first deterministic tool and the proof of the platform spine: it runs
through :func:`~pipeline.shared.containers.run_container`, so every invocation is
digest-pinned, timed as telemetry, and recorded in the biological-provenance audit.
Its JSON report is parsed into the :class:`PreprocessingResult` contract and sealed
with a SHA-256 checksum.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipeline.shared.containers import IMAGE_REGISTRY, ContainerImage, Mount, run_container
from pipeline.shared.observability import RunContext
from pipeline.shared.schemas.base import FileRef
from pipeline.shared.schemas.inputs import FastqPair
from pipeline.shared.schemas.stage1 import (
    ARTIFACT_TYPE,
    FastpFiltering,
    FastpMetrics,
    FastpQc,
    Library,
    PreprocessingArtifact,
    PreprocessingResult,
)

# Reproducible, recorded fastp parameters. These are artifact-floor preprocessing
# choices (quality trim + minimum length), not biological filters.
QUALIFIED_QUALITY_PHRED = 15
LENGTH_REQUIRED = 36
THREADS = 4

STAGE = ARTIFACT_TYPE

# Canonical in-container paths (host files are bind-mounted onto these).
_IN_R1 = "/inputs/in.R1.fastq.gz"
_IN_R2 = "/inputs/in.R2.fastq.gz"
_WORK = "/work"


def _qc(section: Mapping[str, Any]) -> FastpQc:
    return FastpQc(
        total_reads=section["total_reads"],
        total_bases=section["total_bases"],
        q20_rate=section["q20_rate"],
        q30_rate=section["q30_rate"],
    )


def parse_fastp_metrics(report: Mapping[str, Any]) -> FastpMetrics:
    """Extract the QC features we keep from a fastp ``report.json`` (pure/testable)."""
    summary = report["summary"]
    filtering = report["filtering_result"]
    duplication = report.get("duplication", {})
    adapter = report.get("adapter_cutting", {})
    return FastpMetrics(
        before_filtering=_qc(summary["before_filtering"]),
        after_filtering=_qc(summary["after_filtering"]),
        filtering=FastpFiltering(
            passed_filter_reads=filtering["passed_filter_reads"],
            low_quality_reads=filtering.get("low_quality_reads", 0),
            too_many_n_reads=filtering.get("too_many_N_reads", 0),
            too_short_reads=filtering.get("too_short_reads", 0),
            too_long_reads=filtering.get("too_long_reads", 0),
        ),
        duplication_rate=float(duplication.get("rate", 0.0)),
        adapter_trimmed_reads=int(adapter.get("adapter_trimmed_reads", 0)),
    )


def run_fastp(
    library: Library,
    reads: FastqPair,
    *,
    run_ctx: RunContext,
    work_dir: Path | None = None,
    image: ContainerImage | None = None,
) -> PreprocessingArtifact:
    """Run fastp on one library; return a sealed, persisted preprocessing artifact.

    Tool I/O lives on the local filesystem (``work_dir``); the sealed artifact + logs
    go to the run's storage backend (local now, encrypted S3 on AWS).
    """
    image = image or IMAGE_REGISTRY["fastp"]
    work_dir = work_dir or Path("runs") / run_ctx.sample_id / run_ctx.run_id / "qc"
    work_dir.mkdir(parents=True, exist_ok=True)
    paired = reads.r2 is not None

    out_r1 = work_dir / f"{library.value}.trimmed.R1.fastq.gz"
    out_r2 = work_dir / f"{library.value}.trimmed.R2.fastq.gz"
    report_json = work_dir / f"{library.value}.fastp.json"
    report_html = work_dir / f"{library.value}.fastp.html"

    args = ["fastp", "-i", _IN_R1, "-o", f"{_WORK}/{out_r1.name}"]
    mounts = [Mount(Path(reads.r1), _IN_R1, read_only=True), Mount(work_dir, _WORK)]
    inputs = [Path(reads.r1)]
    outputs = [out_r1, report_json, report_html]

    if reads.r2 is not None:
        args += ["-I", _IN_R2, "-O", f"{_WORK}/{out_r2.name}", "--detect_adapter_for_pe"]
        mounts.append(Mount(Path(reads.r2), _IN_R2, read_only=True))
        inputs.append(Path(reads.r2))
        outputs.insert(1, out_r2)

    args += [
        "--json", f"{_WORK}/{report_json.name}",
        "--html", f"{_WORK}/{report_html.name}",
        "--qualified_quality_phred", str(QUALIFIED_QUALITY_PHRED),
        "--length_required", str(LENGTH_REQUIRED),
        "--thread", str(THREADS),
    ]

    completed = run_container(
        image,
        args,
        run_ctx=run_ctx,
        mounts=mounts,
        inputs=inputs,
        outputs=outputs,
        params={
            "library": library.value,
            "qualified_quality_phred": QUALIFIED_QUALITY_PHRED,
            "length_required": LENGTH_REQUIRED,
            "threads": THREADS,
            "detect_adapter_for_pe": paired,
        },
        stage=STAGE,
    )

    metrics = parse_fastp_metrics(json.loads(report_json.read_text()))
    trimmed = [FileRef.from_path(out_r1)]
    if reads.r2 is not None:
        trimmed.append(FileRef.from_path(out_r2))

    result = PreprocessingResult(
        library=library,
        paired_end=paired,
        fastp_version=image.tool_version,
        metrics=metrics,
        trimmed=trimmed,
        report_json=FileRef.from_path(report_json),
        report_html=FileRef.from_path(report_html) if report_html.exists() else None,
    )
    artifact = PreprocessingArtifact(
        artifact_type=ARTIFACT_TYPE,
        sample_id=run_ctx.sample_id,
        provenance=completed.provenance,
        payload=result,
    ).seal()
    run_ctx.write_artifact(artifact, name=f"{ARTIFACT_TYPE}.{library.value}.json")
    return artifact


def main(argv: list[str] | None = None) -> int:
    """Manual smoke runner: ``python -m ...preprocessing --sample S --r1 a --r2 b``."""
    parser = argparse.ArgumentParser(description="Run fastp QC/trim on one FASTQ library.")
    parser.add_argument("--sample", required=True)
    parser.add_argument(
        "--library",
        choices=[lib.value for lib in Library],
        default=Library.TUMOR_DNA.value,
    )
    parser.add_argument("--r1", required=True, type=Path)
    parser.add_argument("--r2", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    run_ctx = RunContext.open(args.sample)
    reads = FastqPair(r1=str(args.r1), r2=str(args.r2) if args.r2 else None)
    artifact = run_fastp(Library(args.library), reads, run_ctx=run_ctx, work_dir=args.work_dir)
    print(artifact.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
