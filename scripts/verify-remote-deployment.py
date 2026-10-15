#!/usr/bin/env python3
"""Check that the two public Studionet deployed code bodies match local source exactly."""
import base64
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
RPC='https://studio.genlayer.com/api'

def rpc(method, params):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    req=urllib.request.Request(
        RPC, data=body,
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'REPROVEX/1.0'},
        method='POST')
    with urllib.request.urlopen(req,timeout=25) as response: doc=json.load(response)
    if doc.get('error') or 'result' not in doc:
        raise ValueError(f'{method} failed: {doc.get("error")}')
    return doc['result']

def check_contract(name,address,tx_hash):
    if not address or len(address)!=42 or not address.startswith('0x'):
        raise ValueError(f'Missing or invalid {name.upper()}_ADDRESS')
    status=rpc('gen_getTransactionStatus',[tx_hash])
    if str(status).upper()!='FINALIZED':
        raise ValueError(f'{name} deployment is not finalized: {status}')
    code=rpc('gen_getContractCode',[address])
    if not isinstance(code,str):
        raise ValueError(f'{name} deployed code is not readable')
    local=(ROOT/'contracts'/('spec_registry.py' if name=='registry' else 'verification_market.py')).read_bytes()
    remote=base64.b64decode(code,validate=True)
    parity=local==remote
    return {'name':name,'address':address,'source_sha256':hashlib.sha256(local).hexdigest(),
            'deployed_sha256':hashlib.sha256(remote).hexdigest(),'exact_parity':parity,
            'explorer':f'https://explorer-studio.genlayer.com/address/{address}'}

def main():
    deployment=json.loads((ROOT/'deployments'/'studionet.json').read_text())
    results=[check_contract('registry',os.environ.get('REGISTRY_ADDRESS',''),deployment['spec_registry']['transaction_hash']),
             check_contract('market',os.environ.get('MARKET_ADDRESS',''),deployment['verification_market']['transaction_hash'])]
    print(json.dumps(results,indent=2))
    if not all(r['exact_parity'] for r in results):raise SystemExit('Deployed source parity FAILED')
    print('Both deployed contracts are exact local source matches; execution flows still require live testing.')

if __name__=='__main__':
    try: main()
    except Exception as e:print(f'UNVERIFIED: {e}',file=sys.stderr);sys.exit(2)
