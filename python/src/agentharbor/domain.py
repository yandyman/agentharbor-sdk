"""Client-side copy of the gateway's domain check, so a bad input fails before any request.

Mirrors x402_gateway/domain.py and DOMAIN_PATTERN in x402_gateway/main.py: a bare public
hostname only (no scheme, port, path, IP literal or reserved TLD). The server checks again.
"""
from __future__ import annotations

import re

from .errors import InvalidDomain

# Same expression the gateway publishes in its OpenAPI/Bazaar input schema.
DOMAIN_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
_DOMAIN_RE = re.compile(DOMAIN_PATTERN)
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BLOCKED_TLDS = frozenset({
    "localhost", "local", "localdomain", "internal", "intranet", "lan", "home", "corp",
    "private", "invalid", "arpa", "onion",
})


def validate_domain(value: object) -> str:
    """Return the normalised (lower-case, no trailing dot) domain or raise InvalidDomain."""
    if not isinstance(value, str):
        raise InvalidDomain("domain must be a string")
    d = value.strip().lower()
    if d.endswith("."):
        d = d[:-1]
    if not d or len(d) > 253:
        raise InvalidDomain("domain is empty or too long")
    if not d.isascii() or re.search(r"[\s/\\:@?#\[\]%]", d):
        raise InvalidDomain(
            f"{value!r} must be a bare hostname such as example.com (no scheme, port or path)")
    labels = d.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels) or not _DOMAIN_RE.match(d):
        raise InvalidDomain(f"{value!r} is not a valid hostname")
    tld = labels[-1]
    if not re.search(r"[a-z]", tld) or tld in _BLOCKED_TLDS:
        raise InvalidDomain(f"{value!r} is not a public hostname")
    if not tld.isalpha() and not tld.startswith("xn--"):
        raise InvalidDomain(f"{value!r} does not end in a valid top-level domain")
    return d
