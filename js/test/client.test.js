import assert from "node:assert/strict";
import { test } from "node:test";

import {
  InvalidDomain, NotCharged, OutcomeUnknown, PaymentFailed, PriceTooHigh, RequestFailed, UnexpectedPayee,
  UnsupportedNetwork, WalletRequired, createAgentHarbor,
} from "../src/index.js";
import { ACCOUNT, OTHER, fakeGateway, fakeX402, paymentRequired, requirement } from "./helpers.js";

const BASE = "https://gw.test";

function setup(gwOpts = {}, clientOpts = {}) {
  const gw = fakeGateway(gwOpts);
  const x = fakeX402();
  const client = createAgentHarbor({ baseUrl: BASE, fetch: gw.fetch, account: ACCOUNT, x402: x.modules, ...clientOpts });
  return { gw, x, client };
}

const hasSig = (r) => r.headers.has("payment-signature");

test("invalid domain fails before any request", async () => {
  const { gw, client } = setup();
  await assert.rejects(client.scrape("https://example.com/"), InvalidDomain);
  assert.equal(gw.requests.length, 0);
});

test("no wallet: WalletRequired with the vetted quote, one request", async () => {
  const gw = fakeGateway({ quote: paymentRequired([requirement({ amount: "5000" })]) });
  const client = createAgentHarbor({ baseUrl: BASE, fetch: gw.fetch });
  await assert.rejects(client.company("example.com"), (e) => {
    assert.ok(e instanceof WalletRequired);
    assert.equal(e.quote.priceUsd, "0.005");
    assert.equal(e.charged, false);
    return true;
  });
  assert.equal(gw.requests.length, 1);
});

test("overpriced quote is refused before signing", async () => {
  const { gw, x, client } = setup({ quote: paymentRequired([requirement({ amount: "100000" })]) });
  await assert.rejects(client.enrich("example.com"), PriceTooHigh);
  assert.equal(x.state.signed, 0);
  assert.deepEqual(gw.requests.map(hasSig), [false]);
});

test("per-call cap overrides the client cap", async () => {
  const { x, client } = setup();
  await assert.rejects(client.scrape("example.com", { maxPriceUsd: 0.005 }), PriceTooHigh);
  assert.equal(x.state.signed, 0);
});

test("wrong payee and testnet quotes are refused before signing", async () => {
  for (const [req, cls] of [[requirement({ payTo: OTHER }), UnexpectedPayee],
    [requirement({ network: "eip155:84532" }), UnsupportedNetwork]]) {
    const { x, client } = setup({ quote: paymentRequired([req]) });
    await assert.rejects(client.scrape("example.com"), cls);
    assert.equal(x.state.signed, 0);
  }
});

test("paid call returns the body with non-enumerable receipt", async () => {
  const { gw, x, client } = setup();
  const r = await client.scrape("Example.COM");
  assert.equal(x.state.signed, 1);
  assert.equal(x.state.registered[0].network, "eip155:8453");
  assert.equal(x.state.registered[0].scheme.signer, ACCOUNT);
  assert.deepEqual(JSON.parse(JSON.stringify(r)), { domain: "example.com", tier: "scrape" });
  assert.equal(r.payment.transaction, "0xabc");
  assert.equal(r.requestId, "rid123");
  assert.equal(r.quote.amountAtomic, "10000");
  assert.deepEqual(gw.requests.map(hasSig), [false, true]);
  assert.equal(new URL(gw.requests[0].url).searchParams.get("domain"), "example.com");
});

test("every method hits its route", async () => {
  for (const [method, path] of [["company", "/company"], ["scrape", "/scrape"], ["aiCrawlers", "/ai-crawlers"],
    ["enrich", "/enrich"], ["audit", "/audit"]]) {
    const { gw, client } = setup();
    await client[method]("example.com");
    assert.deepEqual([...new Set(gw.requests.map((r) => new URL(r.url).pathname))], [path]);
  }
});

test("unusable page: NotCharged with the server detail", async () => {
  const detail = { error: "unusable_result", reason: "bot_block", domain: "example.com", charged: false };
  const g = fakeGateway();
  const { client } = setup({ paid: g.json(422, { detail }) });
  await assert.rejects(client.scrape("example.com"), (e) => {
    assert.ok(e instanceof NotCharged);
    assert.equal(e.status, 422);
    assert.deepEqual(e.detail, detail);
    assert.equal(e.charged, false);
    return true;
  });
});

test("gateway 502 and 409 are NotCharged; route-off 404 too", async () => {
  const g = fakeGateway();
  for (const paid of [g.json(502, { detail: { error: "audit_failed", charged: false } }),
    g.json(409, { error: "payment_in_flight", charged: false })]) {
    const { client } = setup({ paid });
    await assert.rejects(client.audit("example.com"), NotCharged);
  }
  const { client } = setup({ unpaid: g.json(404, { detail: "not found" }) });
  await assert.rejects(client.audit("example.com"), (e) => e instanceof NotCharged && e.detail === "not found");
});

test("Cloudflare 524 after payment: OutcomeUnknown", async () => {
  const { client } = setup({ paid: new Response("<html>timeout</html>", { status: 524 }) });
  await assert.rejects(client.enrich("example.com"), (e) => e instanceof OutcomeUnknown && e.charged === null);
});

test("network failure after payment: OutcomeUnknown; before: RequestFailed", async () => {
  {
    const { client } = setup({ paid: () => { throw new TypeError("fetch failed"); } });
    await assert.rejects(client.enrich("example.com"), OutcomeUnknown);
  }
  {
    const { x, client } = setup({ unpaid: () => { throw new TypeError("fetch failed"); } });
    await assert.rejects(client.enrich("example.com"), (e) => e instanceof RequestFailed && e.charged === false);
    assert.equal(x.state.signed, 0);
  }
});

test("payment rejected (402 again): PaymentFailed with reason", async () => {
  const g = fakeGateway();
  const { client } = setup({ paid: () => g.json(402, {}, { "PAYMENT-REQUIRED": paymentRequired(undefined, { error: "insufficient_funds" }) }) });
  await assert.rejects(client.scrape("example.com"), (e) => e instanceof PaymentFailed && /insufficient_funds/.test(e.message));
});

test("x402 library failure before sending: PaymentFailed", async () => {
  const gw = fakeGateway();
  const x = fakeX402();
  x.modules.wrapFetchWithPayment = (fetch) => async (input, init) => {
    await fetch(new Request(input, init));
    throw new Error("Failed to create payment payload: no balance");
  };
  const client = createAgentHarbor({ baseUrl: BASE, fetch: gw.fetch, account: ACCOUNT, x402: x.modules });
  await assert.rejects(client.scrape("example.com"), PaymentFailed);
});

test("refusal wrapped by the x402 library is still a refusal", async () => {
  const gw = fakeGateway({ quote: paymentRequired([requirement({ amount: "999999" })]) });
  const x = fakeX402();
  x.modules.wrapFetchWithPayment = (fetch) => async (input, init) => {
    try {
      return await fetch(new Request(input, init));
    } catch (e) {
      throw new Error("Failed to parse payment requirements", { cause: e });
    }
  };
  const client = createAgentHarbor({ baseUrl: BASE, fetch: gw.fetch, account: ACCOUNT, x402: x.modules });
  await assert.rejects(client.scrape("example.com"), PriceTooHigh);
});

test("catalog is free and options are validated", async () => {
  const { gw, client } = setup();
  assert.equal((await client.catalog()).provider, "Agent Harbor");
  assert.equal(new URL(gw.requests[0].url).pathname, "/catalog");
  assert.throws(() => createAgentHarbor({ account: ACCOUNT, privateKey: "0x1" }), TypeError);
  assert.throws(() => createAgentHarbor({ maxPriceUsd: -1 }), TypeError);
  assert.equal(client.address, ACCOUNT.address);
  assert.ok(!JSON.stringify(client).includes("private"));
});

test("main entry does not load x402, ai or zod", async () => {
  const src = await import("node:fs").then((fs) => fs.readFileSync(new URL("../src/index.js", import.meta.url), "utf8"));
  assert.ok(!/^import .* from "(@x402\/|viem|ai|zod)/m.test(src));
});
