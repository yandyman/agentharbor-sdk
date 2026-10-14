import assert from "node:assert/strict";
import { test } from "node:test";

import {
  InvalidDomain, MalformedPaymentRequired, PaymentRefused, PriceTooHigh, UnexpectedPayee, UnsupportedNetwork,
  checkPaymentRequired, decodePaymentResponse, makePolicy, usdToAtomic, validateDomain, PAY_TO,
} from "../src/index.js";
import { OTHER, b64json, paymentRequired, requirement } from "./helpers.js";

const SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";

test("valid domains are normalised", () => {
  for (const [v, want] of [["example.com", "example.com"], ["Example.COM.", "example.com"], [" a-b.io ", "a-b.io"],
    ["sub.example.co.uk", "sub.example.co.uk"], ["example.xn--p1ai", "example.xn--p1ai"]]) {
    assert.equal(validateDomain(v), want);
  }
});

test("invalid domains are rejected", () => {
  for (const v of ["", "example", "https://example.com", "example.com/path", "example.com:443", "user@example.com",
    "127.0.0.1", "0x7f.1", "localhost", "printer.local", "db.internal", "-bad.com", "bad-.com", "bücher.de",
    "example.c0m", "a".repeat(64) + ".com", "example..com", "[::1]", null, 42]) {
    assert.throws(() => validateDomain(v), InvalidDomain, String(v));
  }
});

test("decodes a gateway quote", () => {
  const q = checkPaymentRequired(paymentRequired([requirement({ amount: "10000" })]), { maxPriceUsd: 0.05 });
  assert.equal(q.amountAtomic, "10000");
  assert.equal(q.priceUsd, "0.01");
  assert.equal(q.payTo, PAY_TO);
});

test("budget: at the cap passes, above it is refused", () => {
  checkPaymentRequired(paymentRequired([requirement({ amount: "50000" })]), { maxPriceUsd: 0.05 });
  assert.throws(() => checkPaymentRequired(paymentRequired([requirement({ amount: "50001" })]), { maxPriceUsd: 0.05 }),
    PriceTooHigh);
  assert.throws(() => checkPaymentRequired(paymentRequired([requirement({ amount: "10000" })]), { maxPriceUsd: "0.005" }),
    PriceTooHigh);
});

test("payee must match (case-insensitive) and is overridable", () => {
  checkPaymentRequired(paymentRequired([requirement({ payTo: PAY_TO.toLowerCase() })]), { maxPriceUsd: 0.05 });
  assert.throws(() => checkPaymentRequired(paymentRequired([requirement({ payTo: OTHER })]), { maxPriceUsd: 0.05 }),
    UnexpectedPayee);
  checkPaymentRequired(paymentRequired([requirement({ payTo: OTHER })]), { maxPriceUsd: 0.05, payTo: OTHER });
});

test("only exact USDC on Base mainnet", () => {
  for (const r of [requirement({ network: "eip155:84532" }), requirement({ asset: SEPOLIA_USDC }),
    requirement({ scheme: "upto" }), requirement({ network: "solana:mainnet" })]) {
    assert.throws(() => checkPaymentRequired(paymentRequired([r]), { maxPriceUsd: 0.05 }), UnsupportedNetwork);
  }
  assert.throws(() => checkPaymentRequired(paymentRequired([requirement()], { version: 1 }), { maxPriceUsd: 0.05 }),
    UnsupportedNetwork);
});

test("malformed headers are refused", () => {
  for (const h of [null, "", "not base64 !!", b64json([1]), b64json({ x402Version: 2 }),
    b64json({ x402Version: 2, accepts: [] }), paymentRequired([requirement({ amount: "0.01" })])]) {
    assert.throws(() => checkPaymentRequired(h, { maxPriceUsd: 0.05 }), MalformedPaymentRequired, String(h));
  }
});

test("first acceptable requirement wins; most specific refusal is reported", () => {
  const q = checkPaymentRequired(paymentRequired([requirement({ payTo: OTHER }), requirement({ amount: "5000" })]),
    { maxPriceUsd: 0.05 });
  assert.equal(q.amountAtomic, "5000");
  assert.throws(() => checkPaymentRequired(
    paymentRequired([requirement({ network: "eip155:1" }), requirement({ amount: "999999" })]), { maxPriceUsd: 0.05 }),
  PriceTooHigh);
  for (const cls of [PriceTooHigh, UnexpectedPayee, UnsupportedNetwork, MalformedPaymentRequired]) {
    assert.ok(cls.prototype instanceof PaymentRefused);
  }
});

test("usdToAtomic rounds down and rejects bad input", () => {
  assert.equal(usdToAtomic(0.05), 50000n);
  assert.equal(usdToAtomic("0.005"), 5000n);
  assert.equal(usdToAtomic("0.0000019"), 1n);
  assert.equal(usdToAtomic(1e-7), 0n);
  assert.throws(() => usdToAtomic(-1), TypeError);
  assert.throws(() => usdToAtomic("abc"), TypeError);
  assert.throws(() => usdToAtomic(Infinity), TypeError);
});

test("policy keeps only acceptable v2 requirements", () => {
  const policy = makePolicy({ maxPriceUsd: 0.01 });
  const good = requirement({ amount: "10000" });
  assert.deepEqual(policy(2, [requirement({ amount: "20000" }), requirement({ payTo: OTHER }), good]), [good]);
  assert.deepEqual(policy(1, [good]), []);
});

test("decodePaymentResponse", () => {
  assert.deepEqual(decodePaymentResponse(b64json({ transaction: "0xabc" })), { transaction: "0xabc" });
  assert.equal(decodePaymentResponse(null), null);
  assert.equal(decodePaymentResponse("%%%"), null);
});
