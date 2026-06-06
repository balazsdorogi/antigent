"""Platform configuration: reference build, database releases, and storage.

Centralises the few constants that must appear in every provenance record
(DESIGN.md §6.3, §8) plus the env-driven storage configuration that lets the
same code write locally for development and to encrypted S3 on AWS without changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Reference genome build stamped into every Provenance record. Bump deliberately;
# a change here invalidates cross-run comparability and must be auditable.
REFERENCE_BUILD = "GRCh38.p14"

# Pinned external-database releases (knowledge base, annotations). Empty until the
# relevant stages land; recorded in Provenance.db_versions when populated.
DB_VERSIONS: dict[str, str] = {}


@dataclass(frozen=True)
class StorageConfig:
    """Where logs + artifacts are persisted. Resolved from the environment.

    ``backend="local"`` writes under ``root`` on the local filesystem (default).
    ``backend="s3"`` selects the encrypted object-store backend implemented in the
    AWS iteration; the s3 fields are read here but unused until then.
    """

    backend: str = "local"
    root: Path = field(default_factory=lambda: Path("runs"))
    s3_bucket: str | None = None
    s3_prefix: str = "antigent"
    kms_key_id: str | None = None

    @classmethod
    def from_env(cls) -> StorageConfig:
        """Build config from ``ANTIGENT_STORAGE_*`` environment variables."""
        return cls(
            backend=os.environ.get("ANTIGENT_STORAGE_BACKEND", "local"),
            root=Path(os.environ.get("ANTIGENT_STORAGE_ROOT", "runs")),
            s3_bucket=os.environ.get("ANTIGENT_STORAGE_S3_BUCKET"),
            s3_prefix=os.environ.get("ANTIGENT_STORAGE_S3_PREFIX", "antigent"),
            kms_key_id=os.environ.get("ANTIGENT_STORAGE_KMS_KEY_ID"),
        )
