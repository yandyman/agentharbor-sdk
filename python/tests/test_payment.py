from decimal import Decimal
from types import SimpleNamespace

import pytest

from agentharbor import (
    MalformedPaymentRequired,
    PaymentRefused,
    PriceTooHigh,
    UnexpectedPayee,
    UnsupportedNetwork,
    check_payment_required,
)
from agentharbor.payment import (
    PAY_TO,
    USDC_BASE,
    decode_payment_response,
    make_policy,
    usd_to_atomic,
)

from helpers import b64json, payment_required, requirement

SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
OTHER = "0x1111111111111111111111111111111111111111"


def test_decodes_a_gateway_quote():
    q = check_payment_required(payment_required(requirement("10000")), max_price_usd=0.05)
    assert q.amount_atomic == 10000 and q.price_usd == Decimal("0.01")
    assert q.pay_to == PAY_TO and q.network == "eip155:8453" and q.scheme == "exact"
    assert q.as_dict()["price_usd"] == "0.01"


def test_amount_at_the_cap_is_accepted():
    assert check_payment_required(payment_required(requirement("50000")), max_price_usd=0.05).amount_atomic == 50000


def test_amount_above_the_cap_is_refused():
    with pytest.raises(PriceTooHigh) as e:
        check_payment_required(payment_required(requirement("50001")), max_price_usd=0.05)
    assert e.value.quote["amount"] == "50001"
    with pytest.raises(PriceTooHigh):
        check_payment_required(payment_required(requirement("10000")), max_price_usd="0.005")


def test_payee_must_match_but_case_does_not_matter():
    check_payment_required(payment_required(requirement(pay_to=PAY_TO.lower())), max_price_usd=0.05)
    with pytest.raises(UnexpectedPayee):
        check_payment_required(payment_required(requirement(pay_to=OTHER)), max_price_usd=0.05)
    with pytest.raises(UnexpectedPayee):
        check_payment_required(payment_required(requirement(pay_to=OTHER)), max_price_usd=0.05, pay_to=PAY_TO)
    # overridable expected payee
    check_payment_required(payment_required(requirement(pay_to=OTHER)), max_price_usd=0.05, pay_to=OTHER)


@pytest.mark.parametrize("req", [
    requirement(network="eip155:84532"),
    requirement(network="eip155:84532", asset=SEPOLIA_USDC),
    requirement(asset=SEPOLIA_USDC),
    requirement(scheme="upto"),
    requirement(network="solana:mainnet"),
])
def test_only_exact_usdc_on_base_mainnet(req):
    with pytest.raises(UnsupportedNetwork):
        check_payment_required(payment_required(req), max_price_usd=0.05)


def test_x402_v1_is_refused():
    with pytest.raises(UnsupportedNetwork):
        check_payment_required(payment_required(requirement(), version=1), max_price_usd=0.05)


@pytest.mark.parametrize("header", [None, "", "not base64 !!", b64json([1, 2]), b64json({"x402Version": 2}),
                                    b64json({"x402Version": 2, "accepts": []})])
def test_malformed_headers_are_refused(header):
    with pytest.raises(MalformedPaymentRequired):
        check_payment_required(header, max_price_usd=0.05)


def test_non_integer_amount_is_refused():
    with pytest.raises(MalformedPaymentRequired):
        check_payment_required(payment_required(requirement(amount="0.01")), max_price_usd=0.05)


def test_first_acceptable_requirement_wins():
    q = check_payment_required(payment_required(requirement(pay_to=OTHER), requirement("5000")), max_price_usd=0.05)
    assert q.amount_atomic == 5000


def test_most_specific_refusal_is_reported():
    with pytest.raises(PriceTooHigh):
        check_payment_required(payment_required(requirement(network="eip155:1"), requirement("999999")),
                               max_price_usd=0.05)
    with pytest.raises(UnexpectedPayee):
        check_payment_required(payment_required(requirement(scheme="upto"), requirement(pay_to=OTHER)),
                               max_price_usd=0.05)


def test_all_refusals_are_payment_refused():
    for cls in (PriceTooHigh, UnexpectedPayee, UnsupportedNetwork, MalformedPaymentRequired):
        assert issubclass(cls, PaymentRefused)


def test_usd_to_atomic_rounds_down():
    assert usd_to_atomic(0.05) == 50000
    assert usd_to_atomic("0.005") == 5000
    assert usd_to_atomic("0.0000019") == 1
    with pytest.raises(ValueError):
        usd_to_atomic(-1)
    with pytest.raises(ValueError):
        usd_to_atomic("abc")


def test_policy_filters_wire_dicts_and_sdk_objects():
    policy = make_policy(max_price_usd=0.01)
    good, dear, wrong = requirement("10000"), requirement("20000"), requirement(pay_to=OTHER)
    assert policy(2, [dear, wrong, good]) == [good]
    sdk_obj = SimpleNamespace(scheme="exact", network="eip155:8453", asset=USDC_BASE, amount="5000", pay_to=PAY_TO)
    sdk_bad = SimpleNamespace(scheme="exact", network="eip155:8453", asset=USDC_BASE, amount="5000", pay_to=OTHER)
    assert policy(2, [sdk_bad, sdk_obj]) == [sdk_obj]
    assert policy(1, [good]) == []


def test_decode_payment_response():
    assert decode_payment_response(b64json({"transaction": "0xabc"})) == {"transaction": "0xabc"}
    assert decode_payment_response(None) is None
    assert decode_payment_response("%%%") is None
