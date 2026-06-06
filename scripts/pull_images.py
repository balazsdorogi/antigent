"""Pull and verify the digest-pinned tool images; write an audit lock.

For each image in ``IMAGE_REGISTRY``: ``docker pull --platform <p> <pinned-ref>``,
confirm the local RepoDigest contains the pinned digest, and record the outcome in
``infra/docker/images.lock.json`` (the audit record; the registry stays the source of
truth for the pin). Run via ``make pull-images``. Requires a running Docker daemon.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pipeline.shared.containers import IMAGE_REGISTRY, ContainerImage

LOCK_PATH = Path(__file__).resolve().parents[1] / "infra" / "docker" / "images.lock.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _pull_and_inspect(image: ContainerImage) -> tuple[bool, list[str], str]:
    pull = _run(["docker", "pull", "--platform", image.platform, image.ref])
    if pull.returncode != 0:
        return False, [], pull.stderr.strip()
    inspect = _run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image.ref]
    )
    try:
        repo_digests: list[str] = json.loads(inspect.stdout or "[]")
    except json.JSONDecodeError:
        repo_digests = []
    return True, repo_digests, ""


def main() -> int:
    images: dict[str, object] = {}
    any_failed = False

    for name, image in IMAGE_REGISTRY.items():
        ok, repo_digests, error = _pull_and_inspect(image)
        if not ok:
            any_failed = True
            print(f"[FAILED] {name}: {image.ref}\n    {error}")
            continue

        confirmed = image.digest is not None and any(image.digest in d for d in repo_digests)
        marker = "ok" if confirmed else "UNCONFIRMED"
        print(f"[{marker}] {name}: {image.ref}")
        if not confirmed:
            print(f"    pinned digest not found in RepoDigests: {repo_digests}")
        images[name] = {
            "repository": image.repository,
            "tag": image.tag,
            "digest": image.digest,
            "repo_digests": repo_digests,
            "confirmed": confirmed,
        }

    lock = {"generated_at": datetime.now(tz=UTC).isoformat(), "images": images}
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {LOCK_PATH}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
