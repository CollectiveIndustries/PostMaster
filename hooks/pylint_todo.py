#!/usr/bin/env python3
"""
Pre-commit hook: Run pylint once on staged Python files and append a
single FIXME tag at the end of each offending line.
ANSI color codes are removed.
"""

import re
import subprocess
import sys
from pathlib import Path

# Regex to remove ANSI escape codes
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def get_staged_files():
    """Return a list of staged Python files from git."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return [Path(f) for f in result.stdout.splitlines() if f.endswith(".py")]


def run_pylint(files):
    """Run pylint on the given files and return cleaned output."""
    if not files:
        return ""
    result = subprocess.run(
        ["pylint", "--score=no", "--output-format=text", "--reports=no", *map(str, files)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return ansi_escape.sub("", result.stdout + "\n" + result.stderr)


def append_fixme(file_path: Path, lineno: int):
    """Append a single # FIXME pylint comment to the offending line."""
    if not file_path.exists():
        return
    lines = file_path.read_text(encoding="utf-8").splitlines()
    idx = lineno - 1
    if idx >= len(lines):
        return
    comment = "  # FIXME pylint"
    # Don’t duplicate the tag
    if comment not in lines[idx]:
        lines[idx] = lines[idx].rstrip() + comment
        file_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    files = get_staged_files()
    if not files:
        sys.exit(0)

    pylint_output = run_pylint(files)
    pattern = re.compile(r"^(.*\.py):(\d+):\d+: ([A-Z][0-9]+): (.*)$")

    for line in pylint_output.splitlines():
        match = pattern.match(line)
        if match:
            file_path, lineno, _, _ = match.groups()
            append_fixme(Path(file_path), int(lineno))

    # Always exit success so it doesn’t block commits
    sys.exit(0)


if __name__ == "__main__":
    main()
