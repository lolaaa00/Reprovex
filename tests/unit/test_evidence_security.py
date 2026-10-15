import base64
import hashlib
import json
import pytest
from conftest import PIN,SHA,TARGET,TESTER

SOURCE='from genlayer import *\nclass Source(gl.Contract):\n    pass\n'
SPEC='{"rules":[{"id":"RULE1","behavior":"Unauthorized call must fail"}]}'
MANIFEST='{"steps":["Call restricted method without authorization"],"expected":"revert","observed":"success"}'
TX='0x'+'3'*64

def fixture_evidence(env,monkeypatch,model=None):
    m=env.mod
    urls=[PIN.replace('spec.json','source.py'),PIN.replace('spec.json','spec.json'),PIN.replace('spec.json','manifest.json')]
    suite={'source_url':urls[0],'source_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),
           'spec_url':urls[1],'spec_sha256':hashlib.sha256(SPEC.encode()).hexdigest(),
           'target':TARGET,'behavior':'Unauthorized writers must never modify finalized balances'}
    case={'tx_hash':TX,'manifest_url':urls[2], 'manifest_sha256':hashlib.sha256(MANIFEST.encode()).hexdigest(),
          'counter_url':'','counter_sha256':''}
    data={urls[0]:SOURCE,urls[1]:SPEC,urls[2]:MANIFEST}
    def fetch(url,sha,ceiling):
        if sha!=hashlib.sha256(data[url].encode()).hexdigest():raise ValueError('digest mismatch')
        return data[url]
    monkeypatch.setattr(m,'_immutable_evidence',fetch)
    def fake_rpc(method,args):
        if method=='gen_getContractCode':return base64.b64encode(SOURCE.encode()).decode()
        if method=='gen_getTransactionReceipt':return {'id':TX,'recipient':TARGET,'statusName':'Finalized','txExecutionHash':'0x'+'a'*64,'txOrigin':TESTER}
        if method=='gen_dbg_traceTransaction':return {'transaction_id':TX,'result_code':0,'return_data':'0x22','stdout':'Permission granted','stderr':'','genvm_log':[],'eq_outputs':[]}
        raise AssertionError(method)
    monkeypatch.setattr(m,'_json_rpc',fake_rpc)
    value=model or {'verdict':'CONFIRMED','severity':'HIGH','failure_class':'AUTHORITY','violated_rule':'RULE1','explanation':'Unauthorized method succeeded'}
    env.gl.nondet.exec_prompt=lambda prompt, response_format:' '+json.dumps(value)
    return suite,case,data,fake_rpc

def test_independent_receipt_source_trace_grounding(env,monkeypatch):
    suite,case,_,_=fixture_evidence(env,monkeypatch)
    answer=env.mod.evidence_assessment(suite,case)
    assert answer['verdict']=='CONFIRMED' and answer['evidence_valid']
    assert len(answer['proof_root'])==64

def test_source_mismatch_fails_closed(env,monkeypatch):
    suite,case,_,rpc=fixture_evidence(env,monkeypatch)
    monkeypatch.setattr(env.mod,'_json_rpc',lambda method,args:base64.b64encode(b'altered').decode() if method=='gen_getContractCode' else rpc(method,args))
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_unfinalized_receipt_not_paid(env,monkeypatch):
    suite,case,_,rpc=fixture_evidence(env,monkeypatch)
    def altered(method,args):
        result=rpc(method,args)
        if method=='gen_getTransactionReceipt': result=dict(result,statusName='Accepted')
        return result
    monkeypatch.setattr(env.mod,'_json_rpc',altered)
    assert not env.mod.evidence_assessment(suite,case)['evidence_valid']

def test_receipt_target_mismatch_rejected(env,monkeypatch):
    suite,case,_,rpc=fixture_evidence(env,monkeypatch)
    monkeypatch.setattr(env.mod,'_json_rpc',lambda method,args:dict(rpc(method,args),recipient='0x'+'2'*40) if method=='gen_getTransactionReceipt' else rpc(method,args))
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_trace_wrong_tx_rejected(env,monkeypatch):
    suite,case,_,rpc=fixture_evidence(env,monkeypatch)
    monkeypatch.setattr(env.mod,'_json_rpc',lambda method,args:dict(rpc(method,args),transaction_id='0x'+'4'*64) if method=='gen_dbg_traceTransaction' else rpc(method,args))
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_unknown_trace_result_rejected(env,monkeypatch):
    suite,case,_,rpc=fixture_evidence(env,monkeypatch)
    monkeypatch.setattr(env.mod,'_json_rpc',lambda method,args:dict(rpc(method,args),result_code=99) if method=='gen_dbg_traceTransaction' else rpc(method,args))
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_evidence_hash_failure_returns_inconclusive(env,monkeypatch):
    suite,case,data,rpc=fixture_evidence(env,monkeypatch)
    suite['source_sha256']='0'*64
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

@pytest.mark.parametrize('field,value',[('verdict','APPROVE'),('severity','UNDEFINED'),('failure_class','SCAM'),('violated_rule','x'*101)])
def test_malformed_model_field_fails_closed(env,monkeypatch,field,value):
    model={'verdict':'CONFIRMED','severity':'HIGH','failure_class':'AUTHORITY','violated_rule':'RULE1','explanation':'x'}
    model[field]=value
    suite,case,_,_=fixture_evidence(env,monkeypatch,model)
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_weak_severity_cannot_confirm(env,monkeypatch):
    suite,case,_,_=fixture_evidence(env,monkeypatch,{'verdict':'CONFIRMED','severity':'LOW','failure_class':'AUTHORITY','violated_rule':'RULE1'})
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_model_disagreement_not_hidden(env,monkeypatch):
    suite,case,_,_=fixture_evidence(env,monkeypatch)
    first=env.mod.evidence_assessment(suite,case)
    env.gl.nondet.exec_prompt=lambda prompt,response_format:json.dumps({'verdict':'REJECTED','severity':'NONE','failure_class':'NONE','violated_rule':'NONE'})
    second=env.mod.evidence_assessment(suite,case)
    assert first['proof_root']==second['proof_root']
    assert first['verdict']!=second['verdict']

def test_hash_helper(env):
    assert env.mod.digest_ok(b'hello',hashlib.sha256(b'hello').hexdigest())
    assert not env.mod.digest_ok(b'HELLO',hashlib.sha256(b'hello').hexdigest())

def test_pinned_validation(env):
    assert env.mod.pinned_url(PIN)
    assert not env.mod.pinned_url('https://raw.githubusercontent.com/a/b/main/file')
    assert not env.mod.pinned_url(PIN+'?cache=1')

def test_malformed_json_return_inconclusive(env,monkeypatch):
    suite,case,_,_=fixture_evidence(env,monkeypatch)
    env.gl.nondet.exec_prompt=lambda prompt,response_format:'{{invalid json'
    assert env.mod.evidence_assessment(suite,case)['verdict']=='INCONCLUSIVE'

def test_prompt_explicitly_treats_log_as_untrusted(env,monkeypatch):
    suite,case,_,_=fixture_evidence(env,monkeypatch)
    prompts=[]
    env.gl.nondet.exec_prompt=lambda prompt,response_format:(prompts.append(prompt) or {'verdict':'REJECTED','severity':'NONE','failure_class':'NONE','violated_rule':'NONE'})
    env.mod.evidence_assessment(suite,case)
    assert 'UNTRUSTED DATA' in prompts[0]
    assert 'CLAIMANT MANIFEST (untrusted)' in prompts[0]
