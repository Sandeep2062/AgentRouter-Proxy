#!/usr/bin/env python3
"""Compatibility entry point for Anthropic-format clients."""

import os
import runpy
import sys
from pathlib import Path

os.environ["AGENTROUTER_FORMAT"] = "anthropic"
if len(sys.argv) == 1:
    sys.argv.append("4184")
runpy.run_path(str(Path(__file__).with_name("agentrouter-proxy.py")), run_name="__main__")
