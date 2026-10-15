"""Read-only actual Studionet integration. Never mints/fakes local receipts.
Run with finalized REGISTRY_ADDRESS and MARKET_ADDRESS. Missing env skips rather than claiming pass.
"""
import base64
import hashlib
import json
import os
import pathlib
import re
import urllib.request
import pytest

RPC='https://studio.genlayer.com/api'
ROOT=pathlib.Path(__file__).resolve().parents[2]

def call(method,params):
    data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    request=urllib.request.Request(RPC,data=data,method='POST',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=40) as response:
        out=json.load(response)
    assert out.get('error') is None, out.get('error')
    return out['result']

@pytest.mark.parametrize('name,source_file',[('REGISTRY_ADDRESS','spec_registry.py'),('MARKET_ADDRESS','verification_market.py')])
def test_actual_finalized_deployment_code_parity(name,source_file):
    addr=os.environ.get(name,'')
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}',addr):
        pytest.skip(f'Actual finalized {name} not supplied')
    chain=int(call('eth_chainId',[]),16)
    assert chain==61999
    code=call('gen_getContractCode',[{'address':addr,'status':'finalized'}])
    assert base64.b64decode(code,validate=True)==(ROOT/'contracts'/source_file).read_bytes()


def test_actual_finalized_receipt_trace():
    tx=os.environ.get('VERIFIED_TX_HASH','')
    if not re.fullmatch(r'0x[0-9a-fA-F]{64}',tx):
        pytest.skip('No genuine finalized VERIFIED_TX_HASH supplied')
    receipt=call('gen_getTransactionReceipt',[{'txId':tx}])
    assert receipt['id'].lower()==tx.lower()
    assert receipt['statusName'].upper()=='FINALIZED'
    trace=call('gen_dbg_traceTransaction',[{'txID':tx,'round':0}])
    assert trace['transaction_id'].lower()==tx.lower()
    assert trace['result_code'] in [0,1,2]
