# Dockerfile for bg-dict-stardict
#
# Provides every tool needed to build and verify the Bulgarian StarDict
# dictionary from vendor/db.sqlite.xz, so contributors don't have to install
# Python, sdcv, xz, pyglossary etc. on their host machine.
#
# Build the image (only needed once, or after this file changes):
#     docker build -t bg-dict-stardict .
#
# Run any Makefile target inside the container, with the repo mounted at /work:
#     docker run --rm -v "$PWD:/work" -w /work \
#         -u "$(id -u):$(id -g)" bg-dict-stardict make all
#
# The scripts/docker-run.sh wrapper takes care of the boilerplate.

FROM python:3.14-slim

# System tools required by Makefile targets:
#   - make:    drives the build
#   - xz-utils: decompresses vendor/db.sqlite.xz
#   - zip:     packages dist/bulgarian-stardict.zip
#   - sdcv:    used by `make verify` to look up every word
#   - ca-certificates: harmless default, needed if anyone curl-fetches a new dump
# We pin nothing tightly because the apt repo gives us reasonably current
# versions for Debian's stable; the dictionary content is what we care about
# being reproducible, not the toolchain versions.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        make \
        xz-utils \
        zip \
        sdcv \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python packages: the StarDict writer and the .dict.dz compressor.
# Loose floors instead of hard pins so security fixes flow through, but
# major-version drift is bounded.
RUN pip install --no-cache-dir --upgrade \
        "pyglossary>=4.6" \
        "python-idzip>=0.3.9"

# Run as a non-root user by default so files created in /work are owned by
# the invoking user (the wrapper script overrides the UID/GID at run time
# to match the host user).
RUN useradd --create-home --uid 1000 builder
USER builder

WORKDIR /work

# A friendly default that just lists the available make targets.
CMD ["make", "help"]
