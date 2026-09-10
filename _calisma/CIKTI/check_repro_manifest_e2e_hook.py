#!/usr/bin/env python3
"""Dedicated E2E gate for REPRO_ARTIFACT_JOBS override handling."""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
result = subprocess.run([
    sys.executable, "-m", "unittest", "discover", "-s", str(HERE),
    "-p", "test_gen_repro_manifest_e2e.py",
])
sys.exit(result.returncode)
