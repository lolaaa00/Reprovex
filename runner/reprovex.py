#!/usr/bin/env python3
"""REPROVEX command-line inspector and evidence collector. Stdlib only.

This tool reports factual RPC observations. It never creates a consensus verdict
or treats user-provided manifests as proof of a vulnerability.
"""
import argparse
import ast
import base64
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.request
from urllib.error import URLError

RPC = 'https://studio.genlayer.com/api'
HEX_ADDRESS = re.compile(r'^0x[a-fA-F0-9]{40}$')
HEX_TX = re.compile(r'^0x[a-fA-F0-9]{64}$')
PINNED = re.compile(r'^https://raw\.githubusercontent\.com/[^/?#]+/[^/?#]+/[0-9a-f]{40}/[^?#]+$')


class ProbeError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(url: str, limit: int = 100000) -> bytes:
    if not PINNED.fullmatch(url):
        raise ProbeError('only immutable raw GitHub URLs containing a 40-character commit SHA are accepted')
    request = urllib.request.Request(url, headers={'User-Agent': 'Reprovex/1.0'})
    with urllib.request.urlopen(request, timeout=18) as response:
        content = response.read(limit + 1)
    if len(content) > limit or not content:
        raise ProbeError('empty or oversized immutable source')
    return content


def rpc(method: str, params: dict | None, endpoint: str = RPC):
    if endpoint != RPC:
        raise ProbeError('this profile is restricted to canonical Studionet RPC')
    request = urllib.request.Request(endpoint,
        data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': [] if params is None else [params]}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Reprovex/1.0'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            answer = json.load(response)
    except (URLError, OSError, ValueError) as e:
        raise ProbeError(f'{method}: RPC unavailable ({e})') from e
    if not isinstance(answer, dict) or answer.get('error') or 'result' not in answer:
        raise ProbeError(f'{method}: RPC rejected ({str(answer)[:220]})')
    return answer['result']


def analyze(path: pathlib.Path) -> dict:
    source = path.read_bytes()
    tree = ast.parse(source, filename=str(path))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    functions = []
    warnings = []
    checks = {
        'contains_equivalence_principle': b'run_nondet_unsafe' in source or b'prompt_comparative' in source or b'strict_eq' in source,
        'uses_web_evidence': b'nondet.web.' in source,
        'uses_prompt': b'nondet.exec_prompt' in source,
        'receives_gen': b'@gl.public.write.payable' in source,
        'emits_value': b'.emit_transfer(' in source or b'.emit(value=' in source,
        'has_chain_gate': b'chain_id' in source,
        'has_source_pin': b'sha256' in source or b'source_hash' in source,
    }
    for cls in classes:
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [ast.unparse(d) for d in node.decorator_list]
                if any('gl.public.' in name for name in decorators):
                    functions.append({'contract': cls.name, 'method': node.name,
                                      'decorators': decorators, 'line': node.lineno,
                                      'args': [a.arg for a in node.args.args if a.arg != 'self']})
    for name, rule in [('replay', 'replay|duplicate|active_case'), ('authorization', 'sender_address'),
                       ('timeout', 'time.time|datetime'), ('consensus', 'run_nondet|eq_principle')]:
        if not re.search(rule.encode(), source, re.I):
            warnings.append(f'Review missing/unclear {name} handling; heuristic only, not a verified flaw')
    return {'file': str(path), 'sha256': sha256(source), 'bytes': len(source),
            'classes': [c.name for c in classes], 'public_surface': functions,
            'signals': checks, 'review_prompts': warnings}


def verify(suite: dict, tx_hash: str) -> dict:
    if not HEX_ADDRESS.fullmatch(suite.get('target', '')) or not HEX_TX.fullmatch(tx_hash):
        raise ProbeError('invalid target or transaction hash')
    source_data = get(suite['source_url'])
    spec_data = get(suite['spec_url'], 18000)
    deployed = rpc('gen_getContractCode', {'address': suite['target'], 'status': 'finalized'})
    if not isinstance(deployed, str):
        raise ProbeError('deployed code absent')
    decoded = base64.b64decode(deployed, validate=True)
    receipt = rpc('gen_getTransactionReceipt', {'txId': tx_hash})
    trace = rpc('gen_dbg_traceTransaction', {'txID': tx_hash, 'round': 0})
    attestation = {
        'network': 'studionet', 'chain_id': 61999,
        'tx_hash': tx_hash, 'source_sha256': sha256(source_data),
        'spec_sha256': sha256(spec_data), 'deployed_source_sha256': sha256(decoded),
        'source_parity': source_data == decoded,
        'source_pin_valid': sha256(source_data) == suite['source_sha256'],
        'spec_pin_valid': sha256(spec_data) == suite['spec_sha256'],
        'receipt_finalized': str(receipt.get('statusName', '')).upper() == 'FINALIZED',
        'receipt_target_matches': str(receipt.get('recipient', '')).lower() == suite['target'].lower(),
        'receipt_tx_matches': str(receipt.get('id', '')).lower() == tx_hash.lower(),
        'trace_tx_matches': str(trace.get('transaction_id', '')).lower() == tx_hash.lower(),
        'trace_result_code': trace.get('result_code'),
        'trace_return_data': str(trace.get('return_data', ''))[:1800],
        'trace_stderr': str(trace.get('stderr', ''))[:2200],
        'trace_stdout': str(trace.get('stdout', ''))[:2200],
        'captured_utc_seconds': int(time.time()),
    }
    attestation['eligible_for_consensus_review'] = all(attestation[k] for k in (
        'source_parity', 'source_pin_valid', 'spec_pin_valid', 'receipt_finalized',
        'receipt_target_matches', 'receipt_tx_matches', 'trace_tx_matches')) and trace.get('result_code') in (0,1,2)
    return attestation


def matrix(suite: dict) -> dict:
    return {'suite': suite['name'], 'target': suite['target'], 'cases': [
        {'id': 'ACCESS-01', 'title': 'Unauthorized writer', 'method': 'Attempt restricted write from unrelated wallet; compare finalized trace to authorization clause.'},
        {'id': 'REPLAY-02', 'title': 'Repeat commitment', 'method': 'Replay previously consumed nonce/claim; inspect actual contract mutation and finality.'},
        {'id': 'BOUNDARY-03', 'title': 'Numeric extremes', 'method': 'Exercise u256=0, upper bounds and any documented stake caps.'},
        {'id': 'CONSENSUS-04', 'title': 'Malicious leader output', 'method': 'In Direct Mode force leader material output to disagree with validator output; validator must reject.'},
        {'id': 'SOURCE-05', 'title': 'Source / deployed parity', 'method': 'Read finalized deployed code via RPC and compare SHA-256 to immutable source.'},
        {'id': 'EVIDENCE-06', 'title': 'Evidence substitutions', 'method': 'Modify one byte of pinned evidence, assert digest mismatch and fail-closed path.'},
        {'id': 'FINALITY-07', 'title': 'Accepted is not finalized', 'method': 'Submit a write, record accepted and finalized stages and execution result separately.'},
        {'id': 'VALUE-08', 'title': 'Pending credit withdrawal', 'method': 'Withdraw after finalization; prove exactly-once transfer and zero credit, including rejected duplicate.'},
        {'id': 'LIVENESS-09', 'title': 'Stale or inaccessible source', 'method': 'Use unavailable pinned URL; require UNKNOWN/INCONCLUSIVE, never payout.'},
        {'id': 'CHALLENGE-10', 'title': 'Counterevidence opportunity', 'method': 'Submit timely rebuttal and verify it affects independent consensus interpretation.'},
    ]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='REPROVEX | contract testing & real evidence diagnosis')
    sub = p.add_subparsers(dest='command', required=True)
    inspect_cmd = sub.add_parser('inspect', help='inspect GenLayer Python contract AST and risks')
    inspect_cmd.add_argument('files', nargs='+', type=pathlib.Path)
    matrix_cmd = sub.add_parser('matrix', help='create adversarial test plan from suite JSON')
    matrix_cmd.add_argument('suite', type=pathlib.Path)
    verify_cmd = sub.add_parser('verify', help='verify finalized Studionet RPC evidence')
    verify_cmd.add_argument('suite', type=pathlib.Path)
    verify_cmd.add_argument('tx_hash')
    health_cmd = sub.add_parser('health', help='probe canonical Studionet RPC')
    run_cmd = sub.add_parser('run', help='execute real pytest / GenLayer Direct Mode tests; do not fabricate passes')
    run_cmd.add_argument('test_directory', nargs='?', default='tests/direct')
    p.add_argument('--output', type=pathlib.Path)
    args = p.parse_args(argv)
    try:
        if args.command == 'inspect':
            result = [analyze(path) for path in args.files]
        elif args.command == 'matrix':
            result = matrix(json.loads(args.suite.read_text()))
        elif args.command == 'verify':
            result = verify(json.loads(args.suite.read_text()), args.tx_hash)
        elif args.command == 'health':
            result = {'network': 'studionet', 'expected_chain_id': 61999, 'rpc': RPC,
                      'response': rpc('gen_dbg_ping', None)}
            if result['response'] != 'pong':
                raise ProbeError('GenLayer debug ping did not return pong')
        elif args.command == 'run':
            import subprocess
            result = subprocess.run([sys.executable, '-m', 'pytest', args.test_directory, '-v'],
                                    check=False)
            return result.returncode
        else:
            raise ProbeError('unexpected command')
        encoded = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + '\n')
            print(args.output)
        else:
            print(encoded)
        return 0
    except (ValueError, KeyError, OSError, ProbeError) as e:
        print(f'REPROVEX blocked: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
