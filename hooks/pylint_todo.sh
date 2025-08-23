#!/usr/bin/env bash
# This hook reads pylint output and appends a comment to each offending line

set -e

# Run pylint and capture output
PYLINT_OUTPUT=$(pylint "$@" || true)

# Regex: file:line:col: code: message
regex='^(.*\.py):([0-9]+):[0-9]+: ([A-Z][0-9]+): (.*)$'

# Process each line
echo "$PYLINT_OUTPUT" | while IFS= read -r line; do
    if [[ $line =~ $regex ]]; then
        file="${BASH_REMATCH[1]}"
        lineno="${BASH_REMATCH[2]}"
        code="${BASH_REMATCH[3]}"
        message="${BASH_REMATCH[4]}"

        # Escape quotes in message
        message="${message//\"/\\\"}"

        # Append comment to the end of the line using sed
        # Only if the comment isn't already present
        if ! sed -n "${lineno}p" "$file" | grep -q "FIXME pylint: $code"; then
            sed -i "${lineno}s/\$/  # FIXME pylint: $code: $message/" "$file"
        fi
    fi
done
