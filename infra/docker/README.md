# Container conventions

Every deterministic tool runs in its own version-pinned container. There is no
per-call API cost; the only real spend is EC2 compute for heavy alignment, so we keep
images reproducible and run them through one auditable code path.

## Rules

1. **Prefer existing BioContainers / Bioconda images** over building from scratch
   (`quay.io/biocontainers/<tool>`). Author a Dockerfile only when no suitable image
   exists.
2. **Pin by digest, not just tag.** Each image in the registry carries an
   `sha256:` digest (the amd64 manifest digest). `ContainerImage.ref` then resolves to
   `repository@sha256:...`, so a moved tag can never silently change what we run.
3. **Pin `--platform=linux/amd64`.** BioContainers are amd64 and the heavy aligners use
   x86 SIMD. On this Apple-Silicon dev host they run under emulation on **downsampled**
   data; real/benchmark runs happen on **AWS x86_64**. (`run_container` always sets the
   platform flag.)
4. **One runner, always.** Tools are invoked via
   [`pipeline/shared/containers.py`](../../pipeline/shared/containers.py)
   `run_container()`, which records telemetry + a biological-provenance entry (exact
   command, image digest, input/output SHA-256s) for every run. Never shell out to
   `docker` directly from a stage.

## Source of truth

The registry — `IMAGE_REGISTRY` in
[`pipeline/shared/containers.py`](../../pipeline/shared/containers.py) — is the single
source of truth for which images and digests are pinned.

`images.lock.json` (generated, committed) is the **audit record**: when each pinned
image was last pulled and the RepoDigests Docker reported, with a `confirmed` flag
that the pinned digest was present.

## Adding a tool

1. Find the image on quay.io and its amd64 manifest digest, e.g.:
   ```
   curl -s 'https://quay.io/api/v1/repository/biocontainers/<tool>/tag/?onlyActiveTags=true' \
     | python3 -c "import sys,json;[print(t['name'],t['manifest_digest']) for t in json.load(sys.stdin)['tags']]"
   ```
2. Add a `ContainerImage(...)` entry to `IMAGE_REGISTRY` with `tag`, `tool_version`,
   and `digest`.
3. `make pull-images` to pull, verify the digest, and refresh `images.lock.json`.

## Pulling

```
make pull-images   # requires a running Docker daemon
```
