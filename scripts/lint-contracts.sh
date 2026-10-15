#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export GENVM_VERSION=v0.2.12
python -m py_compile contracts/spec_registry.py contracts/verification_market.py runner/reprovex.py
if ! command -v genvm-lint >/dev/null 2>&1; then
  echo 'GenVM linter unavailable; Python syntax verified, semantic verification NOT completed.'
  exit 2
fi
genvm-lint download --version v0.2.12
genvm-lint setup --contract contracts/spec_registry.py
for contract in contracts/spec_registry.py contracts/verification_market.py; do
  genvm-lint lint "$contract" --json
  genvm-lint check "$contract" --json
  genvm-lint validate "$contract" --json
  scripts/strict-typecheck.sh "$contract"
  genvm-lint schema "$contract"
done
