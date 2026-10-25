# agentharbor (JavaScript)

Client for [Agent Harbor](https://agentharbor.agency)'s pay-per-call business-website API at
`https://x402.agentharbor.agency`, paid per request in USDC on Base with [x402](https://www.x402.org).
No account or API key. A client-side budget guard vets every quote before signing, and failed calls
are not charged. Plain ESM JavaScript with TypeScript types, no dependencies of its own; Node 18+.

```bash
npm install agentharbor @x402/fetch @x402/evm viem   # client + x402 payments
npm install ai zod                                   # + Vercel AI SDK tools
```

The x402 packages are optional peer dependencies, loaded with a dynamic `import()` on the first paid
call. Without a wallet the client can still read the free `/catalog` and shows the vetted price of a
paid route (`WalletRequired.quote`).

## Usage

```js
import { createAgentHarbor, NotCharged } from "agentharbor";
import { privateKeyToAccount } from "viem/accounts";

const client = createAgentHarbor({
  account: privateKeyToAccount(process.env.AGENTHARBOR_PRIVATE_KEY),
  maxPriceUsd: 0.05,
});

try {
  const card = await client.company("mailchimp.com");
  console.log(card.business_name, card.generic_email, card.platforms);
  console.log(card.payment, card.requestId); // non-enumerable: receipt and gateway request id
} catch (e) {
  if (e instanceof NotCharged) console.log("not charged:", e.status, e.detail);
  else throw e;
}
```

| Method | Route | Price |
|---|---|---|
| `company(domain)` | `/company` | $0.005 |
| `scrape(domain)` | `/scrape` | $0.01 |
| `aiCrawlers(domain)` | `/ai-crawlers` | $0.01 |
| `enrich(domain)` | `/enrich` | $0.05 |
| `audit(domain)` | `/audit` | $0.05 |
| `catalog()` | `/catalog` | free |

Options: `account` (a viem account or any x402 EVM signer) or `privateKey`; `baseUrl`;
`maxPriceUsd` (default 0.05, also per call: `client.scrape(d, { maxPriceUsd: 0.01 })`); `fetch`;
`timeoutMs` (default 150000); `payTo` (default Agent Harbor's
`0x840C829530DF7B4CCF700Fa3A0060cF2C80b014e`).

## Budget guard

Each paid call goes out unpaid first. The client's inner fetch decodes the 402 `PAYMENT-REQUIRED`
header and runs `checkPaymentRequired` (exported, pure): amount at most `maxPriceUsd`, payee equal
to `payTo`, x402 v2 `exact` USDC on Base mainnet. A failing quote throws `PriceTooHigh`,
`UnexpectedPayee` or `UnsupportedNetwork` before `@x402/fetch` can sign. The same check is
registered as an x402 client policy.

## Errors

All extend `AgentHarborError` and carry `charged` (`false`, or `null` when unknown):
`InvalidDomain`, `PriceTooHigh` / `UnexpectedPayee` / `UnsupportedNetwork` /
`MalformedPaymentRequired` (all `PaymentRefused`), `WalletRequired`, `NotCharged` (`status`,
`detail`), `PaymentFailed`, `RequestFailed`, `OutcomeUnknown` (a signed payment was sent but no
answer arrived; check the payer on basescan.org before retrying).

## Vercel AI SDK

```js
import { generateText } from "ai";
import { agentHarborTools } from "agentharbor/ai";

const result = await generateText({
  model, // any AI SDK language model
  tools: agentHarborTools(client, { include: ["company", "aiCrawlers"] }),
  prompt: "Which AI crawlers does example.com block?",
});
```

`agentHarborTools(client)` returns `tool({ description, inputSchema: z.object({ domain: z.string() }), execute })`
entries keyed `agentharbor_company`, `agentharbor_scrape`, `agentharbor_ai_crawlers`,
`agentharbor_enrich`, `agentharbor_audit`. Descriptions state the price. A failed or refused call
returns `{ error, charged, message }` to the model instead of throwing.

## Support this project

This package is free and MIT licensed. Sponsoring it through
[GitHub Sponsors](https://github.com/sponsors/yandyman) pays for maintenance: keeping it current with
the x402 libraries, fixing bugs, and keeping it free and documented. Sponsorship does not change what
the API costs or how it behaves.

## Links

[API docs (llms.txt)](https://x402.agentharbor.agency/llms.txt) ·
[OpenAPI](https://x402.agentharbor.agency/openapi.json) ·
[Source](https://github.com/yandyman/agentharbor-sdk) · MIT License, Agent Harbor LLC
