#!/usr/bin/env bash
# Build and install sdcv (StarDict console reader) from the upstream source
# at a pinned version.
#
# We don't use the distro's sdcv package because:
#   - Ubuntu noble ships sdcv 0.5.2 (Aug 2017), and that version fails to
#     handle Cyrillic input in certain environments (silently returns no
#     results, or reports "Can not convert <word> to utf8") even when the
#     locale is correctly set.
#   - Pinning the version makes CI deterministic across runner OS upgrades.
#   - sdcv is small and quick to build (~30 seconds on a CI runner).
#
# Usage:
#     ./scripts/install-sdcv.sh           # installs to /usr/local
#     PREFIX=/opt ./scripts/install-sdcv.sh
#
# Requirements (must be available on the host):
#   git, cmake (>= 3.10), a C++11 compiler, glib-2.0 dev headers, zlib dev
#   headers, gettext. On Debian/Ubuntu:
#       sudo apt-get install -y --no-install-recommends \
#           git cmake g++ pkg-config libglib2.0-dev zlib1g-dev gettext

set -euo pipefail

SDCV_VERSION="v0.5.5"
SDCV_REPO="https://github.com/Dushistov/sdcv.git"
PREFIX="${PREFIX:-/usr/local}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo ">> Cloning sdcv $SDCV_VERSION"
git clone --depth 1 --branch "$SDCV_VERSION" "$SDCV_REPO" "$WORKDIR/sdcv"

echo ">> Configuring"
cmake -S "$WORKDIR/sdcv" -B "$WORKDIR/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DWITH_READLINE=OFF \
    -DENABLE_NLS=OFF

echo ">> Building"
cmake --build "$WORKDIR/build" --parallel "$(nproc 2>/dev/null || echo 2)"

echo ">> Installing to $PREFIX"
if [ "$(id -u)" -eq 0 ]; then
    cmake --install "$WORKDIR/build"
else
    sudo cmake --install "$WORKDIR/build"
fi

echo ">> Installed sdcv: $("$PREFIX/bin/sdcv" --version)"
