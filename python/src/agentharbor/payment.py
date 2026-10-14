"""The buyer-side budget guard: pure functions, no network, no x402 SDK.

Before anything is signed, the client decodes the gateway's 402 ``PAYMENT-REQUIRED``
header and runs :func:`check_payment_required` on it. The same per-requirement check is
also registered as an x402 client policy, so the SDK cannot pick a different option.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Callable

from .errors import (
    MalformedPaymentRequired,
    PaymentRefused,
    PriceTooHigh,
    UnexpectedPayee,
    UnsupportedNetwork,
)

#: Agent Harbor's receiving address (published in /catalog, /.well-known/x402 and every 402).
PAY_TO = "0x840C829530DF7B4CCF700Fa3A0060cF2C80b014e"
#: Base mainnet, CAIP-2.
NETWORK = "eip155:8453"
#: USDC on Base mainnet.
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS = 6
X402_VERSION = 2
SCHEME = "exact"


@dataclass(frozen=True)
class Quote:
    """One vetted payment requirement from a 402 challenge."""

    amount_atomic: int
    price_usd: Decimal
    pay_to: str
    network: str
    asset: str
    scheme: str
    requirement: dict = field(repr=False, compare=False, default_factory=dict)

    def as_dict(self) -> dict:
        return {"price_usd": str(self.price_usd), "amount_atomic": str(self.amount_atomic),
                "pay_to": self.pay_to, "network": self.network, "asset": self.asset, "scheme": self.scheme}


def usd_to_atomic(usd: float | str | Decimal) -> int:
    """USD budget to USDC atomic units (6 decimals), rounded down so the cap is never exceeded."""
    try:
        d = Decimal(str(usd))
    except InvalidOperation as e:
        raise ValueError(f"invalid USD amount: {usd!r}") from e
    if d < 0:
        raise ValueError("max_price_usd must not be negative")
    return int((d * (10 ** USDC_DECIMALS)).to_integral_value(rounding=ROUND_DOWN))


def decode_payment_required(header_value: str | None) -> dict:
    """Decode a base64 JSON ``PAYMENT-REQUIRED`` header. Raises MalformedPaymentRequired."""
    if not header_value:
        raise MalformedPaymentRequired("402 without a PAYMENT-REQUIRED header; refusing to pay")
    try:
        raw = base64.b64decode(header_value.strip() + "=" * (-len(header_value.strip()) % 4))
        data = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        raise MalformedPaymentRequired("PAYMENT-REQUIRED header is not base64 JSON; refusing to pay") from e
    if not isinstance(data, dict):
        raise MalformedPaymentRequired("PAYMENT-REQUIRED header is not a JSON object; refusing to pay")
    return data


def _field(req: Any, *names: str) -> Any:
    """Read a requirement field from a dict (camelCase wire form) or an SDK object (snake_case)."""
    for name in names:
        if isinstance(req, dict):
            if name in req:
                return req[name]
        elif hasattr(req, name):
            return getattr(req, name)
    return None


def evaluate_requirement(req: Any, *, max_atomic: int, pay_to: str = PAY_TO,
                         network: str = NETWORK, asset: str = USDC_BASE) -> Quote:
    """Vet one payment requirement. Returns a Quote or raises a PaymentRefused subclass."""
    scheme = _field(req, "scheme")
    net = _field(req, "network")
    req_asset = _field(req, "asset")
    req_pay_to = _field(req, "payTo", "pay_to")
    amount = _field(req, "amount", "maxAmountRequired")
    raw = req if isinstance(req, dict) else {
        "scheme": scheme, "network": net, "asset": req_asset, "payTo": req_pay_to, "amount": amount}

    if scheme != SCHEME or net != network or not isinstance(req_asset, str) or req_asset.lower() != asset.lower():
        raise UnsupportedNetwork(
            f"quote is scheme={scheme!r} network={net!r} asset={req_asset!r}; "
            f"only {SCHEME} USDC on {network} ({asset}) is accepted", raw)
    if not isinstance(req_pay_to, str) or req_pay_to.lower() != pay_to.lower():
        raise UnexpectedPayee(f"quote pays {req_pay_to!r}, expected {pay_to}; refusing to pay", raw)
    if not isinstance(amount, (str, int)) or not str(amount).isdigit():
        raise MalformedPaymentRequired(f"quote amount {amount!r} is not an atomic integer", raw)
    amount_atomic = int(amount)
    price = Decimal(amount_atomic) / (10 ** USDC_DECIMALS)
    if amount_atomic > max_atomic:
        cap = Decimal(max_atomic) / (10 ** USDC_DECIMALS)
        raise PriceTooHigh(f"quoted ${price} exceeds max_price_usd ${cap}; refusing to pay", raw)
    return Quote(amount_atomic, price, req_pay_to, net, req_asset, scheme, dict(raw))


_REFUSAL_ORDER = (PriceTooHigh, UnexpectedPayee, UnsupportedNetwork, MalformedPaymentRequired)


def check_payment_required(header_value: str | None, *, max_price_usd: float | str | Decimal,
                           pay_to: str = PAY_TO, network: str = NETWORK, asset: str = USDC_BASE) -> Quote:
    """Vet a 402 challenge before paying.

    Decodes the ``PAYMENT-REQUIRED`` header and returns the first acceptable requirement as
    a :class:`Quote`. Raises PriceTooHigh, UnexpectedPayee, UnsupportedNetwork or
    MalformedPaymentRequired (all PaymentRefused) when no requirement is acceptable.
    """
    max_atomic = usd_to_atomic(max_price_usd)
    data = decode_payment_required(header_value)
    if data.get("x402Version") != X402_VERSION:
        raise UnsupportedNetwork(f"x402Version {data.get('x402Version')!r} is not supported (need 2)")
    accepts = data.get("accepts")
    if not isinstance(accepts, list) or not accepts:
        raise MalformedPaymentRequired("PAYMENT-REQUIRED has no accepts[]; refusing to pay")
    errors: list[PaymentRefused] = []
    for req in accepts:
        try:
            return evaluate_requirement(req, max_atomic=max_atomic, pay_to=pay_to, network=network, asset=asset)
        except PaymentRefused as e:
            errors.append(e)
    for cls in _REFUSAL_ORDER:   # report the most specific reason
        for e in errors:
            if type(e) is cls:
                raise e
    raise errors[0]


def make_policy(*, max_price_usd: float | str | Decimal, pay_to: str = PAY_TO, network: str = NETWORK,
                asset: str = USDC_BASE) -> Callable[[int, list], list]:
    """An x402 ``PaymentPolicy`` that keeps only requirements passing the same check (v2 only)."""
    max_atomic = usd_to_atomic(max_price_usd)

    def policy(version: int, requirements: list) -> list:
        if version != X402_VERSION:
            return []
        kept = []
        for r in requirements:
            try:
                evaluate_requirement(r, max_atomic=max_atomic, pay_to=pay_to, network=network, asset=asset)
            except PaymentRefused:
                continue
            kept.append(r)
        return kept

    return policy


def decode_payment_response(header_value: str | None) -> dict | None:
    """Decode the ``PAYMENT-RESPONSE`` settlement receipt (transaction hash, payer, network)."""
    if not header_value:
        return None
    try:
        data = json.loads(base64.b64decode(header_value + "=" * (-len(header_value) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None
