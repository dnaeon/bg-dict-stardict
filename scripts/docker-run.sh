#!/usr/bin/env bash
# Run any Makefile target inside the bg-dict-stardict Docker image.
#
# Usage examples:
#     ./scripts/docker-run.sh                  # show available make targets
#     ./scripts/docker-run.sh make all         # build + verify + package
#     ./scripts/docker-run.sh make verify
#     ./scripts/docker-run.sh make refresh-db DUMP=/work/db.sql
#
# The wrapper:
#   - builds the local image on first run (or after Dockerfile changes);
#   - mounts the repo root at /work inside the container;
#   - passes through the host UID/GID so files written to out/, dist/ and
#     vendor/db.sqlite are owned by the invoking user, not by root.
#
# Requires Docker (Desktop on macOS/Windows, the engine on Linux).
# No other dependencies need to be installed on the host.

set -euo pipefail

IMAGE_NAME="bg-dict-stardict:local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not found in PATH." >&2
    echo "       Install Docker Desktop (macOS/Windows) or the docker engine (Linux)." >&2
    echo "       See https://docs.docker.com/get-docker/" >&2
    exit 1
fi

# Build the image if it doesn't exist. We use the local tag
# "bg-dict-stardict:local" so we never collide with any registry-published
# image of the same name. If you change the Dockerfile, run `docker build`
# manually or `docker rmi bg-dict-stardict:local` and re-run this wrapper.
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo ">> Building $IMAGE_NAME (one-time, ~2 minutes)..."
    docker build -t "$IMAGE_NAME" "$REPO_ROOT"
fi

# If no command was given, default to `make help`.
if [ "$#" -eq 0 ]; then
    set -- make help
fi

# On Linux, pass through the host UID/GID so the container writes files
# the host user owns. On macOS and Windows (Docker Desktop), the host
# filesystem layer handles ownership transparently and forcing a UID can
# break PATH lookups; let the image's default 'builder' user run there.
user_args=()
if [ "$(uname -s)" = "Linux" ]; then
    user_args=(-u "$(id -u):$(id -g)")
fi

exec docker run --rm \
    "${user_args[@]}" \
    -v "$REPO_ROOT:/work" \
    -w /work \
    "$IMAGE_NAME" \
    "$@"
