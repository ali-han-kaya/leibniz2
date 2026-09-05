# Reproducible PDF build for this package.
# The repository-level equivalent is docs/Makefile.tectonic.

SHELL := /bin/sh
SOURCE := ingiliz_empirizmi_v3.tex
BUILD_DIR := .build/tectonic
OUTPUT := $(BUILD_DIR)/ingiliz_empirizmi_v3.pdf
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct 2>/dev/null || printf '0')
TECTONIC ?= tectonic

.PHONY: all pdf check clean

all: pdf

pdf:
	@command -v "$(TECTONIC)" >/dev/null 2>&1 || { echo "ERROR: tectonic not found" >&2; exit 2; }
	@test -f "$(SOURCE)" || { echo "ERROR: TeX source not found: $(SOURCE)" >&2; exit 1; }
	@mkdir -p "$(BUILD_DIR)"
	SOURCE_DATE_EPOCH="$(SOURCE_DATE_EPOCH)" "$(TECTONIC)" --keep-logs --outdir "$(BUILD_DIR)" "$(SOURCE)"
	@printf 'built=%s\nsource_date_epoch=%s\nsha256=' "$(OUTPUT)" "$(SOURCE_DATE_EPOCH)"
	@sha256sum "$(OUTPUT)" | awk '{print $$1}'

check: pdf

clean:
	rm -rf "$(BUILD_DIR)"
