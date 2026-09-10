#!/usr/bin/env python3
"""Dedicated E2E gate for reproducibility artifact sections."""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
result = subprocess.run([
    sys.executable, "-m", "unittest", "discover", "-s", str(HERE),
    "-p", "test_repro_artifact_sections_e2e.py",
])
sys.exit(result.returncode)
