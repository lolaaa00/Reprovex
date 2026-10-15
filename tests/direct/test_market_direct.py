"""Native GenVM/Direct Mode smoke tests of the economic contract itself.
No mocked gl.Contract module: requires genlayer-test's actual GenVM SDK.
"""
import json
import pytest
pytest.importorskip('gltest')


def test_market_constructor_metrics(direct_deploy, direct_alice):
    market = direct_deploy('contracts/verification_market.py', direct_alice, sdk_version='v0.2.12')
    m = json.loads(market.get_metrics())
    assert m == {'open_campaigns': 0, 'pending_cases': 0, 'confirmed_cases': 0}
    assert int(market.get_campaign_count()) == 0
    assert int(market.get_case_count()) == 0


def test_market_unfunded_withdraw_fails(direct_deploy, direct_vm, direct_alice):
    market = direct_deploy('contracts/verification_market.py', direct_alice, sdk_version='v0.2.12')
    with direct_vm.expect_revert('no credit'):
        market.withdraw()


def test_market_invalid_campaign_id_is_not_active(direct_deploy, direct_vm, direct_alice):
    market = direct_deploy('contracts/verification_market.py', direct_alice, sdk_version='v0.2.12')
    with direct_vm.expect_revert('campaign not found'):
        market.refund_expired(7)
    assert int(market.get_campaign_count()) == 0


def test_market_invalid_case_id_fails_closed(direct_deploy, direct_vm, direct_alice):
    market = direct_deploy('contracts/verification_market.py', direct_alice, sdk_version='v0.2.12')
    with direct_vm.expect_revert('case not found'):
        market.resolve_case(22)
