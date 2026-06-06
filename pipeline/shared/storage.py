"""Pluggable storage for all observability logs and sealed artifacts.

Both logs and biological artifacts are sensitive, so they share one swappable
destination (mirroring the project's swappable-tool philosophy). Code writes through
:class:`StorageBackend`; switching from local development to encrypted S3 on AWS is a
config change, not a code change.

This round ships :class:`LocalFsBackend` (restrictive perms, FileVault at rest).
:class:`S3Backend` is an honest stub: its data operations raise ``NotImplementedError``
spelling out the SSE-KMS contract the AWS iteration must satisfy.
"""

from __future__ import annotations

import contextlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.shared.config import StorageConfig


class StorageBackend(ABC):
    """Key-addressed blob + append-log store. Keys are ``/``-separated paths."""

    @abstractmethod
    def write_bytes(self, key: str, data: bytes) -> None:
        """Write (overwrite) the blob at ``key``."""

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        """Read the blob at ``key``."""

    @abstractmethod
    def _append_bytes(self, key: str, data: bytes) -> None:
        """Append raw bytes to ``key``, creating it if absent."""

    @abstractmethod
    def location(self, key: str) -> str:
        """Human-readable URI for ``key`` (for logging/provenance)."""

    def append_jsonl(self, key: str, record: Mapping[str, Any]) -> None:
        """Append one canonical JSON line to ``key`` (sorted keys, compact)."""
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        self._append_bytes(key, (line + "\n").encode("utf-8"))

    def open_run(self, sample_id: str, run_id: str) -> RunHandle:
        """Return a handle whose keys are prefixed with ``<sample_id>/<run_id>/``."""
        return RunHandle(backend=self, prefix=f"{sample_id}/{run_id}")


@dataclass(frozen=True)
class RunHandle:
    """A run-scoped view of a backend; relative names get the run prefix."""

    backend: StorageBackend
    prefix: str

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}"

    def write_bytes(self, name: str, data: bytes) -> None:
        self.backend.write_bytes(self._key(name), data)

    def read_bytes(self, name: str) -> bytes:
        return self.backend.read_bytes(self._key(name))

    def append_jsonl(self, name: str, record: Mapping[str, Any]) -> None:
        self.backend.append_jsonl(self._key(name), record)

    def uri(self, name: str) -> str:
        return self.backend.location(self._key(name))


@dataclass
class LocalFsBackend(StorageBackend):
    """Filesystem backend with restrictive perms (dirs 0700, files 0600).

    At-rest protection on the dev host relies on full-disk encryption (FileVault);
    adequate for the synthetic/public data used in development.
    """

    root: Path
    dir_mode: int = 0o700
    file_mode: int = 0o600

    def _path(self, key: str) -> Path:
        return self.root / key

    def _ensure_parent(self, path: Path) -> None:
        """Create missing parent dirs, chmod-ing root and below to ``dir_mode``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        directory = path.parent
        while True:
            with contextlib.suppress(OSError):
                directory.chmod(self.dir_mode)
            if directory == self.root or directory == directory.parent:
                break
            directory = directory.parent

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        self._ensure_parent(path)
        path.write_bytes(data)
        path.chmod(self.file_mode)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def _append_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        self._ensure_parent(path)
        with path.open("ab") as fh:
            fh.write(data)
        path.chmod(self.file_mode)

    def location(self, key: str) -> str:
        return self._path(key).resolve().as_uri()


class S3Backend(StorageBackend):
    """Encrypted object-store backend — implemented in the AWS iteration.

    Data operations intentionally raise ``NotImplementedError`` describing the
    security contract the implementation must honour, so accidental production use of
    an unencrypted path fails loudly rather than silently.
    """

    def __init__(self, *, bucket: str, prefix: str = "antigent", kms_key_id: str | None = None):
        self.bucket = bucket
        self.prefix = prefix
        self.kms_key_id = kms_key_id

    @staticmethod
    def _unimplemented() -> Any:
        raise NotImplementedError(
            "S3Backend lands in the AWS iteration. It must PutObject with SSE-KMS "
            "(ServerSideEncryption=aws:kms, SSEKMSKeyId set), enforce no public access "
            "via bucket policy + Block Public Access, and require TLS in transit "
            "(deny aws:SecureTransport=false). Use the local backend until then."
        )

    def write_bytes(self, key: str, data: bytes) -> None:
        self._unimplemented()

    def read_bytes(self, key: str) -> bytes:
        return self._unimplemented()  # type: ignore[no-any-return]

    def _append_bytes(self, key: str, data: bytes) -> None:
        self._unimplemented()

    def location(self, key: str) -> str:
        return f"s3://{self.bucket}/{self.prefix}/{key}"


def make_storage(config: StorageConfig | None = None) -> StorageBackend:
    """Construct the configured backend (defaults from the environment)."""
    config = config or StorageConfig.from_env()
    if config.backend == "local":
        return LocalFsBackend(root=config.root)
    if config.backend == "s3":
        if not config.s3_bucket:
            raise ValueError("ANTIGENT_STORAGE_S3_BUCKET is required for the s3 backend")
        return S3Backend(
            bucket=config.s3_bucket,
            prefix=config.s3_prefix,
            kms_key_id=config.kms_key_id,
        )
    raise ValueError(f"unknown storage backend: {config.backend!r}")
