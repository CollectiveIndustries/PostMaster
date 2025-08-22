#!/usr/bin/env bash
# Auto-commit any formatting/sorting fixes done by pre-commit

# Stage all changes
git add -A

# Only commit if there is something to commit
if ! git diff --cached --quiet; then
    git commit -m "style: auto-formatting and sorting fixes [pre-commit]" --no-verify
fi
