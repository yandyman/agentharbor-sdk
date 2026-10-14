// The same flow through the real @x402/fetch + @x402/evm and a throwaway viem key (no funds,
// no network). Skipped unless those peer dependencies are installed (CI installs them in one job).
import assert from "node:assert/strict";
import { test } from "node:test";

import { PAY_TO, PriceTooHigh, UnexpectedPayee, createAgentHarbor } from "../src/index.js";
import { OTHER, fakeGateway, paymentRequired, requirement } from "./helpers.js";

let viem = null;
try {
  await import("@x402/fetch");
  await import("@x402/evm/exact/client");
  viem = await import("viem/accounts");
} catch {
  viem = null;
}
const skip = viem ? false : "@x402/fetch, @x402/evm and viem are not installed";

const client = (gw) => createAgentHarbor({
  baseUrl: "https://gw.test", fetch: gw.fetch, account: viem.privateKeyToAccount(viem.generatePrivateKey()),
});

test("real x402 library pays a vetted quote", { skip }, async () => {
  const gw = fakeGateway({ quote: paymentRequired([requirement({ amount: "10000" })]) });
  const r = await client(gw).scrape("example.com");
  assert.equal(r.domain, "example.com");
  const paid = gw.requests.filter((q) => q.headers.has("payment-signature"));
  assert.equal(paid.length, 1);
  const payload = JSON.parse(Buffer.from(paid[0].headers.get("payment-signature"), "base64").toString());
  assert.equal(payload.x402Version, 2);
  assert.equal(payload.accepted.payTo.toLowerCase(), PAY_TO.toLowerCase());
  assert.equal(payload.payload.authorization.to.toLowerCase(), PAY_TO.toLowerCase());
  assert.equal(String(payload.payload.authorization.value), "10000");
});

test("real x402 library never signs a refused quote", { skip }, async () => {
  for (const [req, cls] of [[requirement({ amount: "100000" }), PriceTooHigh], [requirement({ payTo: OTHER }), UnexpectedPayee]]) {
    const gw = fakeGateway({ quote: paymentRequired([req]) });
    await assert.rejects(client(gw).scrape("example.com"), cls);
    assert.ok(!gw.requests.some((q) => q.headers.has("payment-signature")));
  }
});
