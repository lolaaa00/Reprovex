"""Real genlayer-test Direct Mode tests.
These intentionally require the actual GenVM SDK; unit simulations live in tests/unit.
"""
import json
import pytest

pytest.importorskip('gltest')

PIN='https://raw.githubusercontent.com/example/reprovex/'+'1'*40+'/spec.json'
SHA='f'*64
TARGET='0x'+'d'*40
BEHAVIOR='Withdrawals must settle exactly once after the transaction becomes final.'


def test_registry_constructor_and_view(direct_deploy):
    contract=direct_deploy('contracts/spec_registry.py', sdk_version='v0.2.12')
    assert int(contract.get_suite_count())==0


def test_registry_real_direct_register(direct_deploy,direct_vm):
    direct_vm.check_pickling=True
    contract=direct_deploy('contracts/spec_registry.py', sdk_version='v0.2.12')
    index=contract.register_suite('Invariant one',TARGET,PIN,SHA,PIN,SHA,BEHAVIOR,0)
    assert int(index)==1
    stored=json.loads(contract.get_suite(1))
    assert stored['source_url']==PIN
    assert stored['source_sha256']==SHA
    assert stored['target']==TARGET


def test_registry_real_direct_invalid_hash(direct_deploy,direct_vm):
    contract=direct_deploy('contracts/spec_registry.py', sdk_version='v0.2.12')
    with direct_vm.expect_revert('source and spec hashes'):
        contract.register_suite('Invariant one',TARGET,PIN,'X'*64,PIN,SHA,BEHAVIOR,0)


def test_registry_real_direct_cannot_mutate_prior_snapshot(direct_deploy):
    contract=direct_deploy('contracts/spec_registry.py', sdk_version='v0.2.12')
    contract.register_suite('Invariant one',TARGET,PIN,SHA,PIN,SHA,BEHAVIOR,0)
    first=contract.get_suite(1)
    contract.register_suite('Invariant two',TARGET,PIN,SHA,PIN,SHA,BEHAVIOR,0)
    assert contract.get_suite(1)==first
    assert int(contract.get_suite_count())==2
