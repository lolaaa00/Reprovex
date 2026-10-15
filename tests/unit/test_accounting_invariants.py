"""Seeded deterministic economic-state checks (simulated GenLayer context).
Do not confuse these with native GenVM Direct Mode or deployed execution.
"""
import json
import random
import pytest
from conftest import OWNER, TESTER, PIN, SHA, UserError
from test_economic_logic import outcome


def assert_conservation(env):
    campaigns=[json.loads(env.market.get_campaign(i)) for i in range(1,int(env.market.campaign_count)+1)]
    cases=[json.loads(env.market.get_case(i)) for i in range(1,int(env.market.case_count)+1)]
    open_bounties=sum(int(c['bounty_wei']) for c in campaigns if c['state']=='OPEN')
    pending_stakes=sum(int(k['stake_wei']) for k in cases if k['state']=='OPEN')
    credits=int(env.market.get_credit(OWNER))+int(env.market.get_credit(TESTER))
    assert env.market.liabilities==open_bounties+pending_stakes+credits
    assert int(env.market.open_campaigns)==sum(c['state']=='OPEN' for c in campaigns)
    assert int(env.market.pending_cases)==sum(k['state']=='OPEN' for k in cases)
    assert int(env.market.confirmed_cases)==sum(k['verdict']=='CONFIRMED' for k in cases)

@pytest.mark.parametrize('seed', list(range(32)))
def test_seeded_multiple_campaigns_preserve_every_wei(env,monkeypatch,seed):
    rng=random.Random(seed)
    claim_ids=[]
    assert_conservation(env)
    for i in range(4):
        env.gl.message.sender_address=OWNER
        env.gl.message.value=10**18*(i+1)
        campaign=env.market.open_campaign(env.suite,10**16,env.now[0]+10*86400,900)
        env.gl.message.sender_address=TESTER
        env.gl.message.value=10**16*(i+1)
        transaction='0x'+f'{seed*100+i+1:064x}'
        claim=env.market.submit_case(campaign,transaction,PIN,SHA)
        claim_ids.append((campaign,claim,transaction))
        assert_conservation(env)
    env.gl.message.value=0
    env.now[0]+=901
    for campaign,claim,transaction in claim_ids:
        decision=rng.choice(['CONFIRMED','REJECTED','INCONCLUSIVE'])
        monkeypatch.setattr(env.mod,'evidence_assessment',lambda suite,case,d=decision:outcome(d))
        env.market.resolve_case(claim)
        assert_conservation(env)
        if decision=='CONFIRMED':
            with pytest.raises(UserError):
                env.gl.message.value=10**16
                env.market.submit_case(campaign,transaction,PIN,SHA)
            env.gl.message.value=0
    env.now[0]+=11*86400
    for campaign,claim,_ in claim_ids:
        if json.loads(env.market.get_campaign(campaign))['state']=='OPEN':
            env.market.refund_expired(campaign)
            assert_conservation(env)
    for sender in (OWNER,TESTER):
        env.gl.message.sender_address=sender
        if env.market.get_credit(sender):
            before=env.market.liabilities
            owed=env.market.get_credit(sender)
            env.market.withdraw()
            assert env.market.liabilities==before-owed
            assert_conservation(env)
            with pytest.raises(UserError,match='no credit'):
                env.market.withdraw()
    assert env.market.liabilities==0
    assert env.market.dispatched==sum(amount for _,amount in env.sent)
