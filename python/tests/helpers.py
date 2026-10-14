"""Offline test helpers: a fake gateway (httpx.MockTransport) and a fake x402 payer.

The fake payer mimics x402's httpx transport (send unpaid, on 402 sign and retry with
PAYMENT-SIGNATURE) so the tests can prove the guard runs before any signing, without the
x402 SDK or a wallet.
"""
from __future__ import annotations

import base64
import contextlib
import json
from types import SimpleNamespace

import httpx

from agentharbor import client as client_mod
from agentharbor.payment import NETWORK, PAY_TO, USDC_BASE

ACCOUNT = SimpleNamespace(address="0x000000000000000000000000000000000000dEaD")


def b64json(obj) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


def requirement(amount="10000", pay_to=PAY_TO, network=NETWORK, asset=USDC_BASE, scheme="exact"):
    return {"scheme": scheme, "network": network, "amount": amount, "asset": asset, "payTo": pay_to,
            "maxTimeoutSeconds": 300, "extra": {"name": "USD Coin", "version": "2"}}


def payment_required(*accepts, version=2, error=None) -> str:
    body = {"x402Version": version, "accepts": list(accepts) or [requirement()],
            "resource": {"url": "https://x402.agentharbor.agency/scrape"}}
    if error:
        body["error"] = error
    return b64json(body)


class FakeGateway:
    """Answers 402 to unpaid calls and `paid` (a callable or response) to paid ones."""

    def __init__(self, quote: str | None = None, paid=None, unpaid=None):
        self.quote = quote if quote is not None else payment_required()
        self.paid = paid
        self.unpaid = unpaid
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/catalog":
            return httpx.Response(200, json={"provider": "Agent Harbor", "services": []})
        if "payment-signature" in request.headers:
            p = self.paid
            if callable(p):
                return p(request)
            return p or httpx.Response(
                200, json={"domain": request.url.params["domain"], "tier": "scrape"},
                headers={"PAYMENT-RESPONSE": b64json({"success": True, "transaction": "0xabc", "network": NETWORK}),
                         "X-Request-ID": "rid123"})
        if self.unpaid is not None:
            return self.unpaid(request) if callable(self.unpaid) else self.unpaid
        return httpx.Response(402, json={}, headers={"PAYMENT-REQUIRED": self.quote})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


class FakePayer(httpx.AsyncBaseTransport):
    instances: list["FakePayer"] = []

    def __init__(self, account, policy, inner, network):
        self.account, self.policy, self.inner, self.network = account, policy, inner, network
        self.signed = 0
        FakePayer.instances.append(self)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = await self.inner.handle_async_request(request)
        if resp.status_code != 402 or "payment-signature" in request.headers:
            return resp
        await resp.aread()
        required = json.loads(base64.b64decode(resp.headers["payment-required"]))
        allowed = self.policy(2, required["accepts"])
        if not allowed:
            raise RuntimeError("all requirements filtered out by policies")
        self.signed += 1
        headers = dict(request.headers)
        headers["PAYMENT-SIGNATURE"] = b64json({"x402Version": 2, "accepted": allowed[0],
                                                "payload": {"signature": "0xfake"}})
        return await self.inner.handle_async_request(
            httpx.Request(request.method, request.url, headers=headers))

    async def aclose(self) -> None:
        await self.inner.aclose()


@contextlib.contextmanager
def fake_payer():
    FakePayer.instances = []
    original = client_mod._make_payer_transport
    client_mod._make_payer_transport = FakePayer
    try:
        yield FakePayer.instances
    finally:
        client_mod._make_payer_transport = original
