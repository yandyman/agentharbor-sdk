<p align="center">
  <a href="https://agentharbor.agency"><img src="https://agentharbor.agency/img/brand/agent-harbor-logo-horizontal.svg" alt="Agent Harbor" width="240"></a>
</p>

# agentharbor (Python)

Client for [Agent Harbor](https://agentharbor.agency)'s pay-per-call business-website API at
`https://x402.agentharbor.agency`, paid per request in USDC on Base with [x402](https://www.x402.org).
No account or API key. A client-side budget guard vets every quote before signing, and failed calls
are not charged.

```bash
pip install "agentharbor[x402]"              # client + x402 payment support
pip install "agentharbor[x402,langchain]"    # + LangChain tools
```

The base install (`pip install agentharbor`, only `httpx`) can read the free `/catalog` and shows
you the vetted price of a paid route (`WalletRequired.quote`) without paying.

## Usage

```python
import asyncio, os
from agentharbor import AgentHarbor, NotCharged, PriceTooHigh

async def main():
    client = AgentHarbor(private_key=os.environ["AGENTHARBOR_PRIVATE_KEY"], max_price_usd=0.05)
    try:
        card = await client.company("mailchimp.com")
    except NotCharged as e:
        print("not charged:", e.status_code, e.detail)
        return
    print(card["business_name"], card["generic_email"], card["platforms"])
    print(card.payment, card.request_id)   # settlement receipt and gateway request id

asyncio.run(main())
```

| Method | Route | Price |
|---|---|---|
| `company(domain)` | `/company` | $0.005 |
| `scrape(domain)` | `/scrape` | $0.01 |
| `ai_crawlers(domain)` | `/ai-crawlers` | $0.01 |
| `enrich(domain)` | `/enrich` | $0.05 |
| `audit(domain)` | `/audit` | $0.05 |
| `domain_verify(domain)` | `/domain-verify` | $0.005 |
| `sec_company(ticker)` or `sec_company(cik=...)`, `filings=`, `forms=` | `/sec-company` | $0.01 |
| `recalls(category, query, limit=)`; vehicles: `recalls("vehicle", make=, model=, year=)` | `/recalls` | $0.005 |
| `package_check(ecosystem, name, version=None)` | `/package-check` | $0.003 |
| `pdf_extract(url, pages=None)` | `/pdf-extract` | $0.01 |
| `catalog()` | `/catalog` | free |

```python
filing = await client.sec_company("AAPL", filings=5)                 # $0.01
vulns = await client.package_check("pypi", "requests", "2.25.0")     # $0.003
hits = await client.recalls("consumer", "stroller", limit=3)          # $0.005
doc = await client.pdf_extract("https://www.irs.gov/pub/irs-pdf/fw9.pdf", pages="1-2")   # $0.01
```

Paid methods return a `Result`: the JSON body as a plain `dict`, plus `.payment` (decoded
PAYMENT-RESPONSE: transaction hash, network, payer), `.quote` (the vetted price) and `.request_id`.
`/scrape`, `/enrich` and `/company` bodies include a free `content_safety` prompt-injection scan.

`AgentHarborSync` takes the same arguments and has the same methods, without `await`.

### Constructor

```python
AgentHarbor(private_key=None, account=None, base_url="https://x402.agentharbor.agency",
            max_price_usd=0.05, timeout=150, *, pay_to=PAY_TO)
```

- `private_key`: hex EVM key of the paying wallet (USDC on Base). Turned into an `eth_account`
  account immediately; the string is not kept or logged. Or pass `account=` (an `eth_account`
  LocalAccount or any x402 EVM signer).
- `max_price_usd`: the most one call may cost. Each method also takes `max_price_usd=` per call.
- `pay_to`: the only address the client will pay. Defaults to Agent Harbor's
  `0x840C829530DF7B4CCF700Fa3A0060cF2C80b014e`.

## Budget guard

Each paid call is sent unpaid first. The 402 `PAYMENT-REQUIRED` header is decoded and checked by
`agentharbor.check_payment_required` (a pure function): amount at most `max_price_usd`, payee equal
to `pay_to`, x402 v2 `exact` USDC on Base mainnet. A failing quote raises `PriceTooHigh`,
`UnexpectedPayee` or `UnsupportedNetwork` before the x402 SDK can sign. The same check is
registered as an x402 client policy.

## Errors

All errors subclass `AgentHarborError` and carry `.charged` (`False`, or `None` when unknown).

- `InvalidInput`: an argument breaks the route's published input rules (checked client-side, before
  any request). `InvalidDomain` (not a bare public hostname) is a subclass.
- `PaymentRefused` (`PriceTooHigh`, `UnexpectedPayee`, `UnsupportedNetwork`,
  `MalformedPaymentRequired`): the quote failed the guard; nothing signed.
- `WalletRequired`: no wallet configured; `.quote` holds the price.
- `NotCharged`: the gateway answered 4xx/5xx; `.status_code`, `.detail`.
- `PaymentFailed`: the payment was rejected or could not be built; not charged.
- `RequestFailed`: no answer and no payment sent.
- `OutcomeUnknown`: a signed payment was sent but no answer arrived; check the payer address on
  basescan.org before retrying.

## LangChain

```python
from agentharbor import AgentHarbor
from agentharbor.langchain import get_tools

tools = get_tools(AgentHarbor(private_key=..., max_price_usd=0.01), include=["company", "ai_crawlers"])
```

One `StructuredTool` per domain route (`agentharbor_company`, `agentharbor_scrape`,
`agentharbor_ai_crawlers`, `agentharbor_enrich`, `agentharbor_audit`, `agentharbor_domain_verify`),
each with a description that states its price. The other public-data routes are client methods only
for now. Tools return the JSON body as a string; failures become tool errors that say
whether anything was charged.

## Support this project

This package is free and MIT licensed. Sponsoring it through
[GitHub Sponsors](https://github.com/sponsors/yandyman) pays for maintenance: keeping it current with
the x402 libraries, fixing bugs, and keeping it free and documented. Sponsorship does not change what
the API costs or how it behaves.

## Changelog

- **0.2.0**: methods for the public-data routes: `sec_company`, `recalls`, `package_check`,
  `domain_verify`, `pdf_extract` (inputs checked client-side against the gateway's published rules;
  new `InvalidInput` error, parent of `InvalidDomain`); LangChain tool `agentharbor_domain_verify`.
- **0.1.0**: first release: `company`, `scrape`, `ai_crawlers`, `enrich`, `audit`, `catalog`, budget
  guard, LangChain tools.

## Links

[API docs (llms.txt)](https://x402.agentharbor.agency/llms.txt) ·
[OpenAPI](https://x402.agentharbor.agency/openapi.json) ·
[Source](https://github.com/yandyman/agentharbor-sdk) · MIT License, Agent Harbor LLC
