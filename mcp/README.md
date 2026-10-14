# Using Agent Harbor from agents

## Today: the hosted SKILL.md

The gateway serves a skill file that coding agents and agent frameworks can install or read:

**https://x402.agentharbor.agency/SKILL.md** (also at `/.well-known/skill.md`)

It is generated from the same constants as the gateway's 402 challenges, so its prices, network
and payee always match what you will be quoted. It tells an agent when to use each route
(`/company`, `/scrape`, `/enrich`, `/audit`, `/ai-crawlers`), how payment works (x402 v2, scheme
`exact`, USDC on Base mainnet `eip155:8453`, payTo `0x840C829530DF7B4CCF700Fa3A0060cF2C80b014e`),
and how to treat the `content_safety` field.

An agent still needs a way to pay. Options that exist today:

- **Code-running agents**: install this repository's Python (`pip install "agentharbor[x402]"`) or
  JavaScript (`npm install agentharbor @x402/fetch @x402/evm viem`) package. Both enforce a
  per-call budget and refuse quotes that pay anyone but Agent Harbor.
- **Agents with an x402-capable wallet or HTTP tool**: call the routes directly. An unpaid
  `GET https://x402.agentharbor.agency/company?domain=example.com` answers 402 with a base64 JSON
  `PAYMENT-REQUIRED` header; pay and retry. Check the quoted `amount` (6-decimal USDC atomic
  units), `payTo` and `network` before paying.
- **LangChain / Vercel AI SDK agents**: use `agentharbor.langchain.get_tools()` or
  `agentharbor/ai`'s `agentHarborTools()` (see the package READMEs).

Machine-readable references: [`/llms.txt`](https://x402.agentharbor.agency/llms.txt),
[`/openapi.json`](https://x402.agentharbor.agency/openapi.json),
[`/.well-known/x402`](https://x402.agentharbor.agency/.well-known/x402),
[`/catalog`](https://x402.agentharbor.agency/catalog).

## Planned: a remote MCP server

A hosted remote MCP server exposing the same five routes as MCP tools is planned. It does not
exist yet, so there is no URL or client configuration to copy here. This page will be updated with
the endpoint and setup steps when it ships.
