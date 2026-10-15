"""Strict API simulation for isolated accounting/property checks.
NOT a substitute for GenVM Direct Mode, preflight, or real RPC integration.
"""
import importlib.util
import pathlib
import sys
import types
import pytest

ROOT=pathlib.Path(__file__).resolve().parents[2]
OWNER='0x'+'a'*40
TESTER='0x'+'b'*40
OTHER='0x'+'c'*40
TARGET='0x'+'d'*40
PIN='https://raw.githubusercontent.com/example/reprovex/'+'1'*40+'/spec.json'
SHA='f'*64

class TreeMap(dict):
    def __class_getitem__(cls,item):return cls

class Decorator:
    def __call__(self,f):return f
    @property
    def payable(self):return self

class UserError(Exception):pass

class MockVM:
    Return=type('Return',(),{})
    UserError=UserError
    def run_nondet_unsafe(self,leader,validator):
        answer=leader()
        proposal=self.Return()
        proposal.calldata=answer
        if not validator(proposal):raise UserError('Validator rejected material result')
        return answer

class Sender:
    sender_address=OWNER
    origin_address=OWNER
    chain_id=61999
    value=0

class Contract:
    pass

class FakeGl:
    Contract=Contract
    def __init__(self):
        self.vm=MockVM()
        self.public=types.SimpleNamespace(write=Decorator(),view=Decorator())
        self.evm=types.SimpleNamespace(contract_interface=lambda cls:cls)
        self.message=Sender()
        self.message.sender_address=OWNER
        self.message.origin_address=OWNER
        self.message.chain_id=61999
        self.message.value=0
        self.contracts={}
        self.nondet=types.SimpleNamespace(web=types.SimpleNamespace(),exec_prompt=lambda *a,**kw:None)
    def get_contract_at(self,address):return self.contracts[address]

@pytest.fixture
def env(monkeypatch):
    fake=FakeGl()
    module=types.ModuleType('genlayer')
    module.gl=fake
    module.Address=str
    module.u256=int
    module.TreeMap=TreeMap
    monkeypatch.setitem(sys.modules,'genlayer',module)
    def load(name,file):
        spec=importlib.util.spec_from_file_location(name,ROOT/'contracts'/file)
        m=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    regmod=load('reprovex_registry_test','spec_registry.py')
    marketmod=load('reprovex_market_test','verification_market.py')
    registry=regmod.SpecRegistry()
    registry.suites=TreeMap()
    registry.suite_owners=TreeMap()
    suite=registry.register_suite('Complete economic invariant suite',TARGET,PIN,SHA,PIN,SHA,
                                  'Finalized withdrawals are exactly once; paid cases never reopen.',0)
    addr='0x'+'1'*40
    fake.contracts[addr]=types.SimpleNamespace(view=lambda:registry)
    market=marketmod.VerificationMarket(addr)
    market.campaigns=TreeMap()
    market.cases=TreeMap()
    market.active_cases=TreeMap()
    market.credits=TreeMap()
    market.rewarded_tx=TreeMap()
    now=[1770000000]
    monkeypatch.setattr(regmod,'_now',lambda:now[0])
    monkeypatch.setattr(marketmod,'_now',lambda:now[0])
    sent=[]
    class _EOA:
        def __init__(self,address):self.address=address
        def emit_transfer(self,value):sent.append((self.address,value))
    monkeypatch.setattr(marketmod,'_EOA',_EOA)
    return types.SimpleNamespace(gl=fake, registry=registry, market=market,
                                 regmod=regmod,mod=marketmod,now=now,sent=sent,
                                 suite=suite,addr=addr)

@pytest.fixture
def funded(env):
    env.gl.message.value=1000000000000000000
    cid=env.market.open_campaign(env.suite,10000000000000000,env.now[0]+3*86400,900)
    env.gl.message.value=0
    return env,cid

@pytest.fixture
def claimed(funded):
    env,cid=funded
    env.gl.message.sender_address=TESTER
    env.gl.message.value=10000000000000000
    k=env.market.submit_case(cid,'0x'+'3'*64,PIN,SHA)
    env.gl.message.value=0
    return env,cid,k
