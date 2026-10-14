"""Typed errors. Every error says whether you were charged, as far as the client can know."""
from __future__ import annotations

from typing import Any


class AgentHarborError(Exception):
    """Base class for every error raised by this package.

    ``charged`` is ``False`` when no payment can have settled, ``None`` when the
    client cannot know (see :class:`OutcomeUnknown`).
    """

    charged: bool | None = False


class InvalidDomain(AgentHarborError, ValueError):
    """The domain is not a bare public hostname. Raised before any request is made."""


class PaymentRefused(AgentHarborError):
    """The client refused to pay the quote in the 402 challenge. Nothing was signed or sent.

    ``quote`` is the payment requirement the server asked for (a dict), when one could be decoded.
    """

    def __init__(self, message: str, quote: dict | None = None):
        super().__init__(message)
        self.quote = quote


class PriceTooHigh(PaymentRefused):
    """The quoted amount exceeds ``max_price_usd``."""


class UnexpectedPayee(PaymentRefused):
    """The quote asks you to pay an address other than Agent Harbor's."""


class UnsupportedNetwork(PaymentRefused):
    """The quote is not x402 v2 ``exact`` USDC on Base mainnet (eip155:8453)."""


class MalformedPaymentRequired(PaymentRefused):
    """The 402 response had no decodable x402 v2 PAYMENT-REQUIRED header."""


class WalletRequired(AgentHarborError):
    """The route is paid and no wallet was configured. ``quote`` holds the vetted price."""

    def __init__(self, message: str, quote: dict | None = None):
        super().__init__(message)
        self.quote = quote


class PaymentFailed(AgentHarborError):
    """A payment was signed but the server did not accept it (it answered 402 again, or the
    x402 SDK failed to build the payment). The server settles only after serving a call,
    so a rejected payment is not charged."""


class RequestFailed(AgentHarborError):
    """The request never got an answer (DNS, connection, timeout) and no payment had been sent."""


class APIError(AgentHarborError):
    """The server answered 4xx/5xx. ``detail`` is the server's JSON detail (or text)."""

    def __init__(self, message: str, status_code: int, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class NotCharged(APIError):
    """The call failed or the page was unusable (4xx/5xx from the gateway). The gateway
    settles payment only for responses below 400, so you were not charged."""

    charged = False


class OutcomeUnknown(AgentHarborError):
    """A signed payment was sent but no answer from the gateway arrived (client timeout,
    connection error, or a Cloudflare 52x). The server may have served and settled the call.
    Check the payer address on basescan.org before retrying."""

    charged = None
