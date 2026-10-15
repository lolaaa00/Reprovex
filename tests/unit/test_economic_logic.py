import json
import pytest
from conftest import OWNER,TESTER,OTHER,TARGET,PIN,SHA,UserError


def outcome(verdict):
    return {'verdict':verdict,'severity':'HIGH' if verdict=='CONFIRMED' else 'NONE',
            'failure_class':'STATE' if verdict=='CONFIRMED' else 'NONE',
            'violated_rule':'R1' if verdict=='CONFIRMED' else 'NONE',
            'proof_root':'1'*64 if verdict=='CONFIRMED' else '0'*64,
            'evidence_valid':verdict=='CONFIRMED','explanation':'Verified scenario'}

def test_registry_suite_immutable(env):
    old=env.registry.get_suite(1)
    assert json.loads(old)['owner']==OWNER
    env.registry.register_suite('Another complete suite set',TARGET,PIN,SHA,PIN,SHA,
                                'Finalized status must never be guessed by an off-chain caller.',0)
    assert env.registry.get_suite(1)==old
    assert env.registry.get_suite_count()==2

def test_registry_revision_owner_only(env):
    env.gl.message.sender_address=TESTER
    with pytest.raises(UserError,match='only parent author'):env.registry.register_suite('Additional suite',TARGET,PIN,SHA,PIN,SHA,'All withdrawals are FINALIZED before sending.',1)

def test_registry_revision_target_fixed(env):
    with pytest.raises(UserError,match='preserve'):env.registry.register_suite('Additional suite','0x'+'f'*40,PIN,SHA,PIN,SHA,'All withdrawals are FINALIZED before sending.',1)

def test_registry_reject_bad_sha(env):
    with pytest.raises(UserError,match='hashes'):env.registry.register_suite('Third suite',TARGET,PIN,'x'*64,PIN,SHA,'All withdrawals are FINALIZED before sending.',0)

@pytest.mark.parametrize('url',["https://github.com/a/b","http://raw.githubusercontent.com/a/b/"+'1'*40+'/x',"https://raw.githubusercontent.com/a/b/main/x","https://raw.githubusercontent.com/a/b/"+'1'*40+'/x?foo=bar'])
def test_registry_reject_unpinned(env,url):
    with pytest.raises(UserError,match='immutable'):env.registry.register_suite('Third suite',TARGET,url,SHA,PIN,SHA,'All withdrawals are FINALIZED before sending.',0)

def test_list_suites_pagination(env):
    assert [x['id'] for x in json.loads(env.registry.list_suites(1,30))]==[1]
    with pytest.raises(UserError,match='limit'):env.registry.list_suites(1,31)

def test_registry_reject_invalid_target(env):
    with pytest.raises(UserError):env.registry.register_suite('Third suite','0xabc',PIN,SHA,PIN,SHA,'All withdrawals are FINALIZED before sending.',0)

def test_only_owner_funds(env):
    env.gl.message.sender_address=TESTER
    env.gl.message.value=10**18
    with pytest.raises(UserError,match='only specification owner'):env.market.open_campaign(1,10**15,env.now[0]+100000,900)

def test_studionet_gate(env):
    env.gl.message.value=10**18
    env.gl.message.chain_id=61997
    with pytest.raises(UserError,match='studionet'):env.market.open_campaign(1,10**15,env.now[0]+100000,900)

def test_campaign_bounty_liability(funded):
    e,c=funded
    assert c==1
    assert e.market.liabilities==10**18
    assert json.loads(e.market.get_campaign(c))['state']=='OPEN'

@pytest.mark.parametrize('value', [0,10**14,10**23+1])
def test_bounty_range(env,value):
    env.gl.message.value=value
    with pytest.raises(UserError,match='bounty'):env.market.open_campaign(1,10**15,env.now[0]+100000,900)

def test_expiry_bounds(env):
    env.gl.message.value=10**18
    with pytest.raises(UserError,match='deadline'):env.market.open_campaign(1,10**15,env.now[0],900)
    with pytest.raises(UserError,match='deadline'):env.market.open_campaign(1,10**15,env.now[0]+91*86400,900)

def test_sponsor_cannot_file(funded):
    env,cid=funded
    env.gl.message.value=10**16
    with pytest.raises(UserError,match='sponsor'):env.market.submit_case(cid,'0x'+'3'*64,PIN,SHA)

def test_stake_min_and_active(funded):
    env,cid=funded
    env.gl.message.sender_address=TESTER
    env.gl.message.value=1
    with pytest.raises(UserError,match='stake'):env.market.submit_case(cid,'0x'+'3'*64,PIN,SHA)
    env.gl.message.value=10**16
    k=env.market.submit_case(cid,'0x'+'3'*64,PIN,SHA)
    assert k==1 and env.market.liabilities==10**18+10**16
    with pytest.raises(UserError,match='active'):env.market.submit_case(cid,'0x'+'4'*64,PIN,SHA)

def test_reject_bad_transaction(funded):
    env,cid=funded
    env.gl.message.sender_address=TESTER
    env.gl.message.value=10**16
    with pytest.raises(UserError,match='invalid transaction'):env.market.submit_case(cid,'0x123',PIN,SHA)

def test_counterevidence_exclusive(claimed):
    env,cid,k=claimed
    env.gl.message.sender_address=OTHER
    with pytest.raises(UserError,match='only campaign sponsor'):env.market.submit_counterevidence(k,PIN,SHA)
    env.gl.message.sender_address=OWNER
    env.market.submit_counterevidence(k,PIN,SHA)
    assert json.loads(env.market.get_case(k))['counter_url']==PIN
    with pytest.raises(UserError,match='already submitted'):env.market.submit_counterevidence(k,PIN,SHA)

def test_counterevidence_deadline(claimed):
    env,cid,k=claimed
    env.gl.message.sender_address=OWNER
    env.now[0]+=901
    with pytest.raises(UserError,match='window'):env.market.submit_counterevidence(k,PIN,SHA)

def test_resolution_waits(claimed):
    env,cid,k=claimed
    with pytest.raises(UserError,match='still open'):env.market.resolve_case(k)

def test_confirmed_moves_exact_bounty_and_stake(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('CONFIRMED'))
    e.market.resolve_case(k)
    assert e.market.get_credit(TESTER)==10**18+10**16
    assert e.market.liabilities==10**18+10**16
    assert json.loads(e.market.get_campaign(c))['state']=='PAID'
    assert e.market.active_cases[c]==0
    with pytest.raises(UserError,match='already decided'):e.market.resolve_case(k)

def test_rejected_stake_to_sponsor(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('REJECTED'))
    e.market.resolve_case(k)
    assert e.market.get_credit(OWNER)==10**16
    assert e.market.get_credit(TESTER)==0
    assert json.loads(e.market.get_campaign(c))['state']=='OPEN'

def test_inconclusive_returns_stake_no_bounty(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('INCONCLUSIVE'))
    e.market.resolve_case(k)
    assert e.market.get_credit(TESTER)==10**16
    assert json.loads(e.market.get_campaign(c))['state']=='OPEN'

def test_resubmit_after_rejected_case(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('REJECTED'))
    e.market.resolve_case(k)
    e.gl.message.value=10**16
    new=e.market.submit_case(c,'0x'+'4'*64,PIN,SHA)
    assert new==2 and e.market.active_cases[c]==2

def test_no_new_case_after_paid(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('CONFIRMED'))
    e.market.resolve_case(k)
    e.gl.message.value=10**16
    with pytest.raises(UserError,match='closed'):e.market.submit_case(c,'0x'+'4'*64,PIN,SHA)

def test_expired_cannot_refund_active(claimed):
    e,c,k=claimed
    e.now[0]+=4*86400
    with pytest.raises(UserError,match='active report'):e.market.refund_expired(c)

def test_expiry_returns_bounty(funded):
    e,c=funded
    e.now[0]+=4*86400
    e.market.refund_expired(c)
    assert e.market.get_credit(OWNER)==10**18
    with pytest.raises(UserError):e.market.refund_expired(c)

def test_withdraw_exactly_once(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:outcome('CONFIRMED'))
    e.market.resolve_case(k)
    e.market.withdraw()
    assert e.sent==[(TESTER,10**18+10**16)]
    assert e.market.liabilities==0 and e.market.dispatched==10**18+10**16
    with pytest.raises(UserError,match='no credit'):e.market.withdraw()

def test_disallow_false_confirmed_evidence(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    bad=outcome('CONFIRMED');bad['evidence_valid']=False
    monkeypatch.setattr(e.mod,'evidence_assessment',lambda *args:bad)
    with pytest.raises(UserError,match='unsupported payout'):e.market.resolve_case(k)
    assert e.market.get_credit(TESTER)==0

def test_material_validator_disagreement(claimed,monkeypatch):
    e,c,k=claimed
    e.now[0]+=901
    call=[0]
    def disagree(*args):
        call[0]+=1
        return outcome('CONFIRMED' if call[0]==1 else 'REJECTED')
    monkeypatch.setattr(e.mod,'evidence_assessment',disagree)
    with pytest.raises(UserError,match='Validator rejected'):e.market.resolve_case(k)
    assert e.market.get_credit(TESTER)==0
    assert json.loads(e.market.get_case(k))['state']=='OPEN'

def test_address_views_no_arbitrary_credit(funded):
    e,c=funded
    assert e.market.get_credit(OTHER)==0
    assert e.market.get_case(300)==''
    assert e.market.get_campaign(300)==''
