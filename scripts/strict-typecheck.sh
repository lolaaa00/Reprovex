#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -eq 0 ]]; then
  echo "usage: $0 CONTRACT [...]" >&2
  exit 2
fi

for contract in "$@"; do
  output_file="$(mktemp)"
  if genvm-lint typecheck "$contract" --strict >"$output_file" 2>&1; then
    cat "$output_file"
    rm -f "$output_file"
    continue
  else
    status=$?
  fi
  cat "$output_file"

  # genvm-linter 0.11.0 exits with status 1 for strict-mode informational
  # diagnostics even when its final result reports no errors or warnings.
  if grep -Eq '^0 error\(s\), 0 warning\(s\)$' "$output_file"; then
    echo "Accepted genvm-linter strict-mode informational diagnostics for $contract."
    rm -f "$output_file"
    continue
  fi

  rm -f "$output_file"
  exit "$status"
done
