import asyncio
import sys
import types

import httpx
import pytest

from agentharbor import (
    AgentHarbor,
    AgentHarborSync,
    InvalidDomain,
    NotCharged,
    OutcomeUnknown,
    PaymentFailed,
    PriceTooHigh,
    RequestFailed,
    UnexpectedPayee,
    UnsupportedNetwork,
    WalletRequired,
)
from agentharbor import client as client_mod

from helpers import ACCOUNT, FakeGateway, b64json, fake_payer, payment_required, requirement

OTHER = "0x1111111111111111111111111111111111111111"


def run(coro):
    return asyncio.run(coro)


def make(gw, **kw):
    return AgentHarbor(transport=gw.transport(), base_url="https://gw.test", **kw)


# --- before any request -------------------------------------------------------------

def test_invalid_domain_fails_before_any_request():
    gw = FakeGateway()
    with pytest.raises(InvalidDomain):
        run(make(gw).scrape("https://example.com/"))
    assert gw.requests == []


def test_domain_is_normalised_and_sent_as_query_param():
    gw = FakeGateway()
    with fake_payer():
        r = run(make(gw, account=ACCOUNT).scrape("Example.COM."))
    assert r["domain"] == "example.com"
    assert gw.requests[0].url.path == "/scrape" and gw.requests[0].url.params["domain"] == "example.com"


# --- no wallet ----------------------------------------------------------------------

def test_no_wallet_gets_the_vetted_quote():
    gw = FakeGateway(quote=payment_required(requirement("5000")))
    with pytest.raises(WalletRequired) as e:
        run(make(gw).company("example.com"))
    assert e.value.quote["price_usd"] == "0.005" and e.value.charged is False
    assert len(gw.requests) == 1


def test_no_wallet_still_refuses_a_bad_quote():
    gw = FakeGateway(quote=payment_required(requirement(pay_to=OTHER)))
    with pytest.raises(UnexpectedPayee):
        run(make(gw).company("example.com"))


# --- the budget guard runs before signing ---------------------------------------------

def test_overpriced_quote_is_refused_before_signing():
    gw = FakeGateway(quote=payment_required(requirement("100000")))   # $0.10
    with fake_payer() as payers:
        with pytest.raises(PriceTooHigh):
            run(make(gw, account=ACCOUNT, max_price_usd=0.05).enrich("example.com"))
    assert payers[0].signed == 0
    assert len(gw.requests) == 1 and "payment-signature" not in gw.requests[0].headers


def test_per_call_cap_overrides_the_client_cap():
    gw = FakeGateway(quote=payment_required(requirement("10000")))
    with fake_payer() as payers:
        with pytest.raises(PriceTooHigh):
            run(make(gw, account=ACCOUNT).scrape("example.com", max_price_usd=0.005))
    assert payers[0].signed == 0


def test_wrong_payee_is_refused_before_signing():
    gw = FakeGateway(quote=payment_required(requirement(pay_to=OTHER)))
    with fake_payer() as payers:
        with pytest.raises(UnexpectedPayee):
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert payers[0].signed == 0


def test_testnet_quote_is_refused_before_signing():
    gw = FakeGateway(quote=payment_required(requirement(network="eip155:84532")))
    with fake_payer() as payers:
        with pytest.raises(UnsupportedNetwork):
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert payers[0].signed == 0


def test_refusal_wrapped_by_the_sdk_is_still_a_refusal():
    class WrappingPayer(httpx.AsyncBaseTransport):
        def __init__(self, account, policy, inner, network):
            self.inner = inner

        async def handle_async_request(self, request):
            try:
                return await self.inner.handle_async_request(request)
            except Exception as e:
                raise RuntimeError("Failed to handle payment") from e

    gw = FakeGateway(quote=payment_required(requirement("999999")))
    original = client_mod._make_payer_transport
    client_mod._make_payer_transport = WrappingPayer
    try:
        with pytest.raises(PriceTooHigh):
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    finally:
        client_mod._make_payer_transport = original


# --- paid path ---------------------------------------------------------------------------

def test_paid_call_returns_body_with_receipt():
    gw = FakeGateway(quote=payment_required(requirement("10000")))
    with fake_payer() as payers:
        r = run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert payers[0].signed == 1 and payers[0].network == "eip155:8453"
    assert r == {"domain": "example.com", "tier": "scrape"} and isinstance(r, dict)
    assert r.payment["transaction"] == "0xabc" and r.request_id == "rid123"
    assert r.quote.amount_atomic == 10000
    assert [("payment-signature" in q.headers) for q in gw.requests] == [False, True]


@pytest.mark.parametrize("method,path", [("company", "/company"), ("scrape", "/scrape"), ("enrich", "/enrich"),
                                         ("audit", "/audit"), ("ai_crawlers", "/ai-crawlers")])
def test_every_method_hits_its_route(method, path):
    gw = FakeGateway()
    with fake_payer():
        run(getattr(make(gw, account=ACCOUNT), method)("example.com"))
    assert {q.url.path for q in gw.requests} == {path}


# --- error mapping -----------------------------------------------------------------------

def test_unusable_page_is_not_charged_and_carries_the_detail():
    detail = {"error": "unusable_result", "reason": "bot_block", "domain": "example.com", "charged": False}
    gw = FakeGateway(paid=httpx.Response(422, json={"detail": detail}))
    with fake_payer():
        with pytest.raises(NotCharged) as e:
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert e.value.status_code == 422 and e.value.detail == detail and e.value.charged is False


def test_gateway_502_is_not_charged():
    gw = FakeGateway(paid=httpx.Response(502, json={"detail": {"error": "audit_failed", "charged": False}}))
    with fake_payer():
        with pytest.raises(NotCharged):
            run(make(gw, account=ACCOUNT).audit("example.com"))


def test_in_flight_409_is_not_charged():
    gw = FakeGateway(paid=httpx.Response(409, json={"error": "payment_in_flight", "charged": False}))
    with fake_payer():
        with pytest.raises(NotCharged) as e:
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert e.value.detail["error"] == "payment_in_flight"


def test_404_route_off_is_not_charged():
    gw = FakeGateway(unpaid=httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(NotCharged) as e:
        run(make(gw).audit("example.com"))
    assert e.value.detail == "not found"


def test_cloudflare_timeout_after_payment_is_outcome_unknown():
    gw = FakeGateway(paid=httpx.Response(524, text="<html>A timeout occurred</html>"))
    with fake_payer():
        with pytest.raises(OutcomeUnknown) as e:
            run(make(gw, account=ACCOUNT).enrich("example.com"))
    assert e.value.charged is None


def test_client_timeout_after_payment_is_outcome_unknown():
    def paid(request):
        raise httpx.ReadTimeout("timed out", request=request)
    gw = FakeGateway(paid=paid)
    with fake_payer():
        with pytest.raises(OutcomeUnknown):
            run(make(gw, account=ACCOUNT).enrich("example.com"))


def test_connection_error_before_payment_is_request_failed():
    def unpaid(request):
        raise httpx.ConnectError("refused", request=request)
    gw = FakeGateway(unpaid=unpaid)
    with fake_payer() as payers:
        with pytest.raises(RequestFailed) as e:
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert payers[0].signed == 0 and e.value.charged is False


def test_rejected_payment_is_payment_failed():
    gw = FakeGateway(paid=lambda r: httpx.Response(
        402, json={}, headers={"PAYMENT-REQUIRED": payment_required(error="insufficient_funds")}))
    with fake_payer():
        with pytest.raises(PaymentFailed) as e:
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    assert "insufficient_funds" in str(e.value)


def test_sdk_failure_before_sending_is_payment_failed():
    class X402Error(Exception):
        pass
    X402Error.__module__ = "x402.http.clients.httpx"

    class BrokenPayer(httpx.AsyncBaseTransport):
        def __init__(self, account, policy, inner, network):
            self.inner = inner

        async def handle_async_request(self, request):
            await self.inner.handle_async_request(request)
            raise X402Error("Failed to handle payment: no balance")

    gw = FakeGateway()
    original = client_mod._make_payer_transport
    client_mod._make_payer_transport = BrokenPayer
    try:
        with pytest.raises(PaymentFailed):
            run(make(gw, account=ACCOUNT).scrape("example.com"))
    finally:
        client_mod._make_payer_transport = original


# --- free routes, sync wrapper, key handling ------------------------------------------------

def test_catalog_is_free():
    gw = FakeGateway()
    assert run(make(gw).catalog())["provider"] == "Agent Harbor"
    assert gw.requests[0].url.path == "/catalog"


def test_sync_wrapper():
    gw = FakeGateway()
    with fake_payer():
        client = AgentHarborSync(account=ACCOUNT, transport=gw.transport())
        assert client.scrape("example.com")["tier"] == "scrape"
        assert client.catalog()["provider"] == "Agent Harbor"
    assert "AgentHarborSync(" in repr(client) and client.address == ACCOUNT.address


def test_private_key_is_not_kept_or_echoed():
    secret = "0x" + "ab" * 32
    fake = types.ModuleType("eth_account")

    class Account:
        @staticmethod
        def from_key(key):
            if key != secret:
                raise ValueError(f"bad key {key}")
            return types.SimpleNamespace(address="0x00000000000000000000000000000000000000AA")

    fake.Account = Account
    saved = sys.modules.get("eth_account")
    sys.modules["eth_account"] = fake
    try:
        c = AgentHarbor(private_key=secret)
        assert secret not in repr(c) and secret not in str(vars(c))
        with pytest.raises(ValueError) as e:
            AgentHarbor(private_key="0xdeadbeef")
        assert "deadbeef" not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__
    finally:
        if saved is None:
            del sys.modules["eth_account"]
        else:
            sys.modules["eth_account"] = saved


def test_private_key_and_account_are_exclusive():
    with pytest.raises(ValueError):
        AgentHarbor(private_key="0x1", account=ACCOUNT)


def test_package_imports_without_the_x402_extra():
    # A fresh interpreter: other test modules (and pytest collection) may already have imported x402.
    import os
    import subprocess

    src = os.path.join(os.path.dirname(__file__), "..", "src")
    code = "import sys, agentharbor, agentharbor.client, agentharbor.payment; assert 'x402' not in sys.modules, 'x402 imported eagerly'"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [os.path.abspath(src), os.environ.get("PYTHONPATH")]))}
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
