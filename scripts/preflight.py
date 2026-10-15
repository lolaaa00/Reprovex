#!/usr/bin/env python3
"""Strict deployment preflight: report missing checks as BLOCKED, not green."""
import hashlib
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RPC = 'https://studio.genlayer.com/api'
EXPECTED_CHAIN_ID = 61999
EXPECTED_CLI = '0.39.1'

def result(name, ok, detail):
    return {'check': name, 'pass': bool(ok), 'detail': str(detail)[:350]}

def rpc_call(method, params, timeout=16):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    request = urllib.request.Request(RPC, data=payload, method='POST',
                                     headers={'Content-Type': 'application/json',
                                              'Accept': 'application/json',
                                              'User-Agent': 'REPROVEX-Preflight/1.0'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        document = json.load(response)
    if document.get('error') or 'result' not in document:
        raise RuntimeError(str(document.get('error', 'missing result')))
    return document['result']

def run(cmd, timeout=120):
    try:
        process = subprocess.run(cmd, cwd=ROOT, timeout=timeout, capture_output=True, text=True)
        return process.returncode == 0, (process.stdout + process.stderr).strip()[-350:]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)

def main(argv=None):
    offline = '--offline' in (argv or sys.argv[1:])
    checks = []
    for filename in ('spec_registry.py', 'verification_market.py'):
        path = ROOT / 'contracts' / filename
        code = path.read_text()
        expected_header = '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'
        checks.append(result('GenVM runtime '+filename, code.splitlines()[0] == expected_header,
                             'exact pinned runtime; SHA256='+hashlib.sha256(code.encode()).hexdigest()))
    root = json.loads((ROOT/'package.json').read_text())
    checks.append(result('repo-local CLI package pin', root.get('devDependencies', {}).get('genlayer') == EXPECTED_CLI,
                         root.get('devDependencies', {}).get('genlayer')))
    cli = ROOT/'node_modules'/'.bin'/'genlayer'
    checks.append(result('installed repo CLI', cli.is_file(), 'Missing: npm install' if not cli.is_file() else str(cli)))
    if cli.is_file():
        ok, out = run([str(cli), '--version'], timeout=10)
        checks.append(result('CLI executable version', ok and EXPECTED_CLI in out, out))
    for name in ('pytest', 'gltest'):
        checks.append(result('Python package '+name, importlib.util.find_spec(name) is not None,
                             'required for real Direct Mode' if name == 'gltest' else 'needed for test suite'))
    checks.append(result('GenVM linter available', shutil.which('genvm-lint') is not None,
                         'Install genvm-linter; SDK validation must complete'))
    checks.append(result('web dependencies installed', (ROOT/'frontend'/'node_modules'/'next').is_dir(),
                         'npm --prefix frontend install'))
    if not offline:
        try:
            chain = rpc_call('eth_chainId', [])
            checks.append(result('Studionet RPC available', bool(chain), chain))
            checks.append(result('chain ID', int(chain, 16) == EXPECTED_CHAIN_ID, chain))
            # Full authoritative schema extraction (does not deploy/sign).
            for filename in ('spec_registry.py', 'verification_market.py'):
                src = (ROOT/'contracts'/filename).read_bytes()
                schema = rpc_call('gen_getContractSchemaForCode', ['0x' + src.hex()], timeout=40)
                checks.append(result('GenVM deployed-code schema '+filename,
                                     isinstance(schema, dict) and bool(schema.get('methods')),
                                     'real GenVM compilation/schema extraction'))
        except Exception as exc:
            checks.append(result('RPC/schema preflight', False, str(exc)))
    if shutil.which('genvm-lint'):
        for filename in ('spec_registry.py', 'verification_market.py'):
            ok, out = run(['genvm-lint', 'check', 'contracts/'+filename, '--json'], timeout=120)
            checks.append(result('SDK semantic lint '+filename, ok, out))
    output = {'project': 'REPROVEX', 'network': 'studionet', 'rpc': RPC,
              'offline': offline, 'overall': 'PASS' if all(c['pass'] for c in checks) else 'BLOCKED',
              'checks': checks}
    print(json.dumps(output, indent=2))
    return 0 if output['overall'] == 'PASS' else 2

if __name__ == '__main__':
    sys.exit(main())
