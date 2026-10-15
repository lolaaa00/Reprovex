import base64
import hashlib
import importlib.util
import json
import pathlib
import pytest
from conftest import ROOT,PIN,TARGET

sp=importlib.util.spec_from_file_location('reprovex_runner',ROOT/'runner'/'reprovex.py')
runner=importlib.util.module_from_spec(sp)
sp.loader.exec_module(runner)

def test_contract_inspection_has_real_methods():
    source=runner.analyze(ROOT/'contracts'/'verification_market.py')
    assert 'VerificationMarket' in source['classes']
    methods={f['method'] for f in source['public_surface']}
    assert {'open_campaign','submit_case','resolve_case','withdraw','get_credit'}<=methods
    assert source['signals']['contains_equivalence_principle']

def test_digest_matches_stdlib():
    assert runner.sha256(b'hello')==hashlib.sha256(b'hello').hexdigest()

def test_matrix_10_scenarios():
    plan=runner.matrix({'name':'Contract A','target':TARGET})
    assert len(plan['cases'])==10
    assert len({c['id'] for c in plan['cases']})==10

def test_rpc_rejects_foreign_endpoint():
    with pytest.raises(runner.ProbeError,match='canonical'):runner.rpc('gen_getContractCode',{},endpoint='https://evil.example')

def test_remote_source_requires_commit():
    with pytest.raises(runner.ProbeError,match='immutable'):runner.get('https://raw.githubusercontent.com/a/b/main/a.py')

def test_probe_invalid_tx_before_network():
    with pytest.raises(runner.ProbeError,match='invalid'):runner.verify({'target':TARGET},'0xdead')

def test_probe_detects_source_drift(monkeypatch):
    src=b'from genlayer import *\n'
    manifest=b'{"rules":[]}'
    def get(url,limit=100000):return src if url.endswith('.py') else manifest
    def rpc(method,params,endpoint=runner.RPC):
        if method=='gen_getContractCode':return base64.b64encode(b'wrong source').decode()
        if method=='gen_getTransactionReceipt':return {'statusName':'Finalized','recipient':TARGET,'id':'0x'+'3'*64}
        return {'transaction_id':'0x'+'3'*64,'result_code':0}
    monkeypatch.setattr(runner,'get',get)
    monkeypatch.setattr(runner,'rpc',rpc)
    suite={'target':TARGET,'source_url':PIN.replace('spec.json','source.py'),'source_sha256':runner.sha256(src),'spec_url':PIN,'spec_sha256':runner.sha256(manifest)}
    result=runner.verify(suite,'0x'+'3'*64)
    assert result['source_pin_valid']
    assert not result['deployedMatchesPinned'] if 'deployedMatchesPinned' in result else not result['source_parity']
    assert not result['eligible_for_consensus_review']
