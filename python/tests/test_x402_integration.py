"""The same flow through the real x402 SDK and a throwaway key (no funds, no network).

Skipped unless the ``x402`` extra is installed (CI installs it in one job). Signing an
EIP-3009 authorization is local, so the fake gateway can inspect the real payment header.
"""
import asyncio
import base64
import json

import pytest

pytest.importorskip("x402")
eth_account = pytest.importorskip("eth_account")

from agentharbor import PAY_TO, AgentHarbor, PriceTooHigh, UnexpectedPayee  # noqa: E402

from helpers import FakeGateway, payment_required, requirement  # noqa: E402

OTHER = "0x1111111111111111111111111111111111111111"


def _client(gw, **kw):
    return AgentHarbor(account=eth_account.Account.create(), transport=gw.transport(),
                       base_url="https://gw.test", **kw)


def test_real_sdk_pays_a_vetted_quote():
    gw = FakeGateway(quote=payment_required(requirement("10000")))
    r = asyncio.run(_client(gw).scrape("example.com"))
    assert r["domain"] == "example.com" and r.payment["transaction"] == "0xabc"
    paid = [q for q in gw.requests if "payment-signature" in q.headers]
    assert len(paid) == 1
    payload = json.loads(base64.b64decode(paid[0].headers["payment-signature"]))
    assert payload["x402Version"] == 2
    assert payload["accepted"]["payTo"].lower() == PAY_TO.lower()
    auth = payload["payload"]["authorization"]
    assert auth["to"].lower() == PAY_TO.lower() and int(auth["value"]) == 10000


@pytest.mark.parametrize("req,err", [(requirement("100000"), PriceTooHigh), (requirement(pay_to=OTHER), UnexpectedPayee)])
def test_real_sdk_never_signs_a_refused_quote(req, err):
    gw = FakeGateway(quote=payment_required(req))
    with pytest.raises(err):
        asyncio.run(_client(gw).scrape("example.com"))
    assert not any("payment-signature" in q.headers for q in gw.requests)
