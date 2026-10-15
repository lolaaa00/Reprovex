#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/node_modules/.bin:$PATH"
[ -x node_modules/.bin/genlayer ] || { echo 'Missing repository-local genlayer@0.39.1. Run npm ci or npm install in this directory.'; exit 2; }
VERSION="$(genlayer --version 2>&1)"
echo "CLI: $VERSION"
[[ "$VERSION" == *"0.39.1"* ]] || { echo 'Refusing CLI version other than 0.39.1'; exit 2; }
echo 'Target: stable Studionet 61999 https://studio.genlayer.com/api'
echo 'Confirm your active local CLI account has enough faucet GEN to fund BOTH deployment fees.'
genlayer network set studionet
genlayer network info
if [[ -z "${REGISTRY_ADDRESS:-}" ]]; then
  echo 'STEP 1: deploy immutable specification registry. Copy the finalized address from the output.'
  genlayer deploy --contract contracts/spec_registry.py --rpc https://studio.genlayer.com/api
  echo 'Once fully finalized, re-run with REGISTRY_ADDRESS=0x... to deploy the verification market.'
else
  [[ "$REGISTRY_ADDRESS" =~ ^0x[0-9a-fA-F]{40}$ ]] || { echo 'Invalid REGISTRY_ADDRESS'; exit 2; }
  echo 'STEP 2: deploying VerificationMarket with finalized SpecRegistry address.'
  genlayer deploy --contract contracts/verification_market.py --rpc https://studio.genlayer.com/api --args "$REGISTRY_ADDRESS"
  echo 'Copy market address from finalized receipt into frontend/.env.local (see .env.example).'
fi
