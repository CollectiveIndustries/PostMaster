#!/usr/bin/env python3
"""
Pre-commit hook to run pylint once, and append a FIXME comment to the end of each offending line.
"""

import re
import subprocess
import sys
from pathlib import Path

# Collect files from pre-commit
files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
if not files:
    sys.exit(0)

# Run pylint once on all files
result = subprocess.run(["pylint", *map(str, files)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

pylint_output = result.stdout + "\n" + result.stderr

# Example pylint line: FrostWardenSanctum.py:12:4: W1203: Use lazy % formatting in logging functions
pattern = re.compile(r"^(.*\.py):(\d+):\d+: ([A-Z][0-9]+): (.*)$")

for line in pylint_output.splitlines():
    match = pattern.match(line)
    if match:
        file_path, lineno, code, message = match.groups()
        file_path = Path(file_path)
        lineno = int(lineno)

        # Append FIXME comment to the end of the line, avoid duplicates
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            idx = lineno - 1
            comment = f"  # FIXME pylint: {code}: {message}"
            if idx < len(lines) and comment not in lines[idx]:
                lines[idx] += comment
                file_path.write_text("\n".join(lines), encoding="utf-8")

# Exit with pylint's exit code so pre-commit knows if it failed
sys.exit(result.returncode)
