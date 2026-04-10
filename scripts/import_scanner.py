#!/usr/bin/env python3
"""
Pre-commit friendly Python import scanner.

- Scans Python files recursively or from glob/staged files.
- Deduplicates imports and installs missing packages via pip.
- Skips .venv directories.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path


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


def find_python_files(files=None):
    """Return all Python files from given list or recursively from CWD."""
    if files:
        # Use provided files/globs
        python_files = [Path(f) for f in files if Path(f).suffix == ".py" and ".venv" not in Path(f).parts]
    else:
        # Recursively from CWD, skip .venv
        python_files = [f for f in Path.cwd().rglob("*.py") if ".venv" not in f.parts]
    return python_files


def extract_imports(file_path: Path):
    """Extract top-level module names from import statements."""
    imports = set()
    import_pattern = re.compile(r'^\s*(?:import|from)\s+([\w_]+)')
    try:
        with file_path.open(encoding="utf-8") as f:
            for line in f:
                match = import_pattern.match(line)
                if match:
                    module = match.group(1).split(".")[0]  # top-level module
                    imports.add(module)
    except Exception as e:
        print(f"[WARN] Could not read {file_path}: {e}")
    return imports


def ensure_module(module_name: str):
    """Try to import, if fails pip install."""
    if importlib.util.find_spec(module_name) is None:
        print(f"[MISSING] {module_name}, installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", module_name], check=False)
    else:
        print(f"[OK] {module_name} is already installed")


def main():
    # Determine files to scan
    if len(sys.argv) > 1:
        python_files = find_python_files(sys.argv[1:])
    else:
        python_files = get_staged_files()
        if not python_files:
            python_files = find_python_files()  # fallback to full repo scan

    # Collect imports
    all_imports = set()
    for py_file in python_files:
        all_imports.update(extract_imports(py_file))

    print(f"Found {len(all_imports)} unique modules.")
    for module in sorted(all_imports):
        ensure_module(module)


if __name__ == "__main__":
    main()
