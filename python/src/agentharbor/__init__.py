"""Client for Agent Harbor's pay-per-call x402 API (USDC on Base).

    from agentharbor import AgentHarbor
    client = AgentHarbor(private_key=os.environ["AGENTHARBOR_PRIVATE_KEY"], max_price_usd=0.05)
    card = await client.company("example.com")
"""
from ._tools import PRICES_USD, TOOL_SPECS, ToolSpec
from ._version import __version__
from .client import DEFAULT_BASE_URL, AgentHarbor, AgentHarborSync, Result
from .domain import DOMAIN_PATTERN, validate_domain
from .errors import (
    AgentHarborError,
    APIError,
    InvalidDomain,
    MalformedPaymentRequired,
    NotCharged,
    OutcomeUnknown,
    PaymentFailed,
    PaymentRefused,
    PriceTooHigh,
    RequestFailed,
    UnexpectedPayee,
    UnsupportedNetwork,
    WalletRequired,
)
from .payment import NETWORK, PAY_TO, USDC_BASE, Quote, check_payment_required

__all__ = [
    "AgentHarbor", "AgentHarborSync", "Result", "Quote", "DEFAULT_BASE_URL",
    "check_payment_required", "validate_domain", "DOMAIN_PATTERN",
    "PAY_TO", "NETWORK", "USDC_BASE", "PRICES_USD", "TOOL_SPECS", "ToolSpec",
    "AgentHarborError", "InvalidDomain", "PaymentRefused", "PriceTooHigh", "UnexpectedPayee",
    "UnsupportedNetwork", "MalformedPaymentRequired", "WalletRequired", "PaymentFailed",
    "APIError", "NotCharged", "OutcomeUnknown", "RequestFailed",
    "__version__",
]
