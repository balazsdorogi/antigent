"""Digest-pinned container registry + the reusable docker runner.

Every deterministic tool runs through :func:`run_container`, which builds the exact
``docker run`` command (recorded verbatim for provenance), times the call as telemetry,
resolves the image digest, hashes inputs/outputs, and writes one biological-provenance
record. This is the convention every tool wrapper reuses (DESIGN.md §6b).

Local policy: pin ``--platform=linux/amd64`` (BioContainers are amd64; heavy aligners
use x86 SIMD) and emulate on downsampled data; real/benchmark runs happen on AWS x86_64.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.shared.config import DB_VERSIONS, REFERENCE_BUILD
from pipeline.shared.observability import RunContext
from pipeline.shared.schemas.base import FileRef, Provenance


@dataclass(frozen=True)
class ContainerImage:
    """A version-pinned tool image. ``digest`` is the amd64 manifest sha256."""

    name: str
    repository: str
    tag: str
    tool_version: str
    digest: str | None = None
    platform: str = "linux/amd64"

    @property
    def tagged_ref(self) -> str:
        return f"{self.repository}:{self.tag}"

    @property
    def ref(self) -> str:
        """Digest-pinned reference when locked, else the tag reference."""
        return f"{self.repository}@{self.digest}" if self.digest else self.tagged_ref

    @property
    def is_pinned(self) -> bool:
        return self.digest is not None


# Single source of truth for pinned tool images. Digests are amd64 manifest digests
# from quay.io; `make pull-images` verifies each pulls and writes an audit lock.
IMAGE_REGISTRY: dict[str, ContainerImage] = {
    "fastp": ContainerImage(
        name="fastp",
        repository="quay.io/biocontainers/fastp",
        tag="0.24.1--heae3180_0",
        tool_version="0.24.1",
        digest="sha256:99eb308e4c4f1a6467beb775019bce0f88414303395fa8f27ad6da9a014bf14b",
    ),
}


@dataclass(frozen=True)
class Mount:
    """A host->container bind mount."""

    source: Path
    target: str
    read_only: bool = False

    def to_args(self) -> list[str]:
        suffix = ":ro" if self.read_only else ""
        return ["-v", f"{Path(self.source).resolve()}:{self.target}{suffix}"]


@dataclass
class CompletedRun:
    """Result of a container run, including the recorded provenance."""

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    provenance: Provenance


class ContainerRunError(RuntimeError):
    """Raised when a checked container run exits non-zero (provenance is recorded)."""

    def __init__(self, result: CompletedRun) -> None:
        self.result = result
        super().__init__(
            f"{result.provenance.tool} exited {result.exit_code} "
            f"({result.provenance.image}): {result.stderr.strip()[:500]}"
        )


def _build_command(
    image: ContainerImage,
    args: Sequence[str],
    *,
    mounts: Sequence[Mount],
    workdir: str | None,
    docker_bin: str,
) -> list[str]:
    cmd = [docker_bin, "run", "--rm", "--platform", image.platform]
    if workdir:
        cmd += ["-w", workdir]
    for mount in mounts:
        cmd += mount.to_args()
    cmd.append(image.ref)
    cmd += list(args)
    return cmd


def _resolve_digest(image: ContainerImage, docker_bin: str) -> str:
    """Best-effort actual RepoDigest of the image used (truthful provenance)."""
    try:
        proc = subprocess.run(
            [docker_bin, "image", "inspect", "--format", "{{index .RepoDigests 0}}", image.ref],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return image.digest or "unresolved"
    if proc.returncode == 0 and "@" in proc.stdout:
        return proc.stdout.strip().split("@", 1)[1]
    return image.digest or "unresolved"


def run_container(
    image: ContainerImage,
    args: Sequence[str],
    *,
    run_ctx: RunContext,
    mounts: Sequence[Mount] = (),
    workdir: str | None = None,
    inputs: Sequence[Path] = (),
    outputs: Sequence[Path] = (),
    params: Mapping[str, Any] | None = None,
    stage: str | None = None,
    docker_bin: str = "docker",
    check: bool = True,
) -> CompletedRun:
    """Run a tool container; record telemetry + provenance; return the result.

    ``inputs`` are hashed before the run and ``outputs`` after, into the provenance
    FileRefs. The exact command is recorded verbatim. Raises :class:`ContainerRunError`
    on a non-zero exit when ``check`` is True (provenance is still recorded first).
    """
    command = _build_command(image, args, mounts=mounts, workdir=workdir, docker_bin=docker_bin)
    input_refs = [FileRef.from_path(p) for p in inputs]

    with run_ctx.telemetry.tool_run(image.name, image=image.ref) as metrics:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        metrics.exit_code = proc.returncode

    output_refs = [FileRef.from_path(p) for p in outputs if Path(p).exists()]
    provenance = Provenance(
        tool=image.name,
        tool_version=image.tool_version,
        image=image.ref,
        image_digest=_resolve_digest(image, docker_bin),
        reference_build=REFERENCE_BUILD,
        db_versions=dict(DB_VERSIONS),
        command=command,
        inputs=input_refs,
        outputs=output_refs,
        params=dict(params or {}),
    )
    run_ctx.provenance.record(provenance, stage=stage)

    result = CompletedRun(
        command=command,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        provenance=provenance,
    )
    if check and proc.returncode != 0:
        raise ContainerRunError(result)
    return result
