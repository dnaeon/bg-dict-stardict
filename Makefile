# Top-level Makefile for bg-dict-stardict.
#
# Convenience entry points around the Python scripts in scripts/. No tool
# installation is performed here; the targets assume the prerequisites
# listed in README.md are already present on the system.
#
# Targets:
#   make build          - build the StarDict dictionary from vendor/db.sqlite
#   make verify         - exhaustively verify the built dictionary
#   make package        - zip the built dictionary into dist/bulgarian-stardict.zip
#   make test           - run unit tests
#   make refresh-db     - re-run dump_to_sqlite.py against a fresh dump
#                         (pass DUMP=/path/to/db.sql)
#   make clean          - remove build outputs (keeps vendor/db.sqlite)
#   make distclean      - clean + drop dist/
#   make all            - build + verify + package

SHELL := /bin/bash

ROOT          := $(CURDIR)
SCRIPTS       := $(ROOT)/scripts
VENDOR_DB_XZ  := $(ROOT)/vendor/db.sqlite.xz
VENDOR_DB     := $(ROOT)/vendor/db.sqlite
OUT_DIR       := $(ROOT)/out/stardict/bulgarian
DIST_ZIP      := $(ROOT)/dist/bulgarian-stardict.zip
DICT_FILES    := $(OUT_DIR)/bulgarian.ifo \
                 $(OUT_DIR)/bulgarian.idx \
                 $(OUT_DIR)/bulgarian.dict.dz \
                 $(OUT_DIR)/bulgarian.syn

PYTHON        ?= python3
DOCKER_RUN    := $(SCRIPTS)/docker-run.sh

.PHONY: all build verify package test refresh-db clean distclean help \
        docker-all docker-build docker-verify docker-package

all: build verify package  ## build, verify and package (default)

help:  ## show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / { printf "  %-22s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

build: $(DICT_FILES)  ## build the StarDict dictionary from vendor/db.sqlite

# Decompress vendor/db.sqlite.xz on demand. The committed source is the .xz
# (compressed ~27 MB) - the decompressed .sqlite (~250 MB) is regenerated
# locally as needed and gitignored.
$(VENDOR_DB): $(VENDOR_DB_XZ)
	xz -dk --force $(VENDOR_DB_XZ)

$(DICT_FILES): $(VENDOR_DB) $(SCRIPTS)/build_stardict.py $(SCRIPTS)/format_meaning.py
	$(PYTHON) $(SCRIPTS)/build_stardict.py

verify:  ## exhaustively verify the built dictionary against vendor/db.sqlite
	@if [ ! -f "$(OUT_DIR)/bulgarian.ifo" ]; then \
		echo "Built dictionary not found. Run 'make build' first." >&2; \
		exit 1; \
	fi
	$(PYTHON) $(SCRIPTS)/verify_stardict.py

package: $(DIST_ZIP)  ## zip the built dictionary into dist/bulgarian-stardict.zip

$(DIST_ZIP): $(DICT_FILES)
	@mkdir -p $(dir $(DIST_ZIP))
	@rm -f $(DIST_ZIP)
	cd $(dir $(OUT_DIR)) && zip -qr $(DIST_ZIP) $(notdir $(OUT_DIR)) \
		-x '*/*.oft' '*/*.clt' '*/.DS_Store'
	@echo "Packaged: $(DIST_ZIP)"

test:  ## run unit tests
	$(PYTHON) -m unittest discover -s tests -v

refresh-db:  ## re-import vendor/db.sqlite.xz from a fresh MySQL dump (DUMP=path/to/db.sql)
ifndef DUMP
	$(error Usage: make refresh-db DUMP=/path/to/db.sql)
endif
	$(PYTHON) $(SCRIPTS)/dump_to_sqlite.py $(DUMP) $(VENDOR_DB)
	xz -9 --force $(VENDOR_DB)
	@echo "Wrote $(VENDOR_DB_XZ). Commit it to update the vendored database."

clean:  ## remove build outputs and the decompressed vendor/db.sqlite (keeps the .xz)
	rm -rf $(ROOT)/out
	rm -f $(VENDOR_DB)

distclean: clean  ## clean + drop dist/
	rm -rf $(ROOT)/dist

# --- Docker convenience targets ---------------------------------------------
# Each runs the corresponding native target inside the Docker image. The
# wrapper script handles building the image on first run, mounting the repo
# and passing UID/GID through on Linux.

docker-all:  ## build, verify and package inside Docker
	$(DOCKER_RUN) make all

docker-build:  ## build the StarDict dictionary inside Docker
	$(DOCKER_RUN) make build

docker-verify:  ## exhaustively verify the built dictionary inside Docker
	$(DOCKER_RUN) make verify

docker-package:  ## zip the built dictionary inside Docker
	$(DOCKER_RUN) make package
