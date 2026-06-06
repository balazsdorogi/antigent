"""Shared pytest fixtures.

Genomic test data is generated at runtime into ``tmp_path`` — never committed —
honoring the project rule to never commit raw genomic data (and `.gitignore` ignores
``*.fastq*`` anyway).
"""

import gzip
import random
from pathlib import Path

import pytest


def _write_fastq_gz(path: Path, *, n_reads: int, read_len: int, seed: int) -> None:
    rng = random.Random(seed)
    with gzip.open(path, "wt") as fh:
        for i in range(n_reads):
            seq = "".join(rng.choice("ACGT") for _ in range(read_len))
            fh.write(f"@read{i}\n{seq}\n+\n{'I' * read_len}\n")


@pytest.fixture
def synthetic_fastq_pair(tmp_path):
    """A tiny paired-end FASTQ.gz set generated at runtime (downsampled dev data)."""
    r1 = tmp_path / "reads.R1.fastq.gz"
    r2 = tmp_path / "reads.R2.fastq.gz"
    _write_fastq_gz(r1, n_reads=200, read_len=100, seed=1)
    _write_fastq_gz(r2, n_reads=200, read_len=100, seed=2)
    return r1, r2
