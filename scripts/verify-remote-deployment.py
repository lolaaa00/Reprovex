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

def check_contract(name,address):
    if not address or len(address)!=42 or not address.startswith('0x'):
        raise ValueError(f'Missing or invalid {name.upper()}_ADDRESS')
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':'gen_getContractCode',
                     'params':[{'address':address,'status':'finalized'}]}).encode()
    req=urllib.request.Request(RPC,data=body,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=25) as response: doc=json.load(response)
    if doc.get('error') or not isinstance(doc.get('result'),str):
        raise ValueError(f'{name} is not finalized/readable: {doc.get("error")}')
    local=(ROOT/'contracts'/('spec_registry.py' if name=='registry' else 'verification_market.py')).read_bytes()
    remote=base64.b64decode(doc['result'],validate=True)
    parity=local==remote
    return {'name':name,'address':address,'source_sha256':hashlib.sha256(local).hexdigest(),
            'deployed_sha256':hashlib.sha256(remote).hexdigest(),'exact_parity':parity,
            'explorer':f'https://explorer-studio.genlayer.com/address/{address}'}

def main():
    results=[check_contract('registry',os.environ.get('REGISTRY_ADDRESS','')),
             check_contract('market',os.environ.get('MARKET_ADDRESS',''))]
    print(json.dumps(results,indent=2))
    if not all(r['exact_parity'] for r in results):raise SystemExit('Deployed source parity FAILED')
    print('Both deployed contracts are exact local source matches; execution flows still require live testing.')

if __name__=='__main__':
    try: main()
    except Exception as e:print(f'UNVERIFIED: {e}',file=sys.stderr);sys.exit(2)
