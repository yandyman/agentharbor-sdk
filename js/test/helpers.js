// Offline test helpers: a fake gateway (an injected fetch) and fake x402 modules that mimic
// @x402/fetch (send unpaid; on 402 apply policies, sign, retry with PAYMENT-SIGNATURE).
import { NETWORK, PAY_TO, USDC_BASE } from "../src/guard.js";

export const ACCOUNT = { address: "0x000000000000000000000000000000000000dEaD" };
export const OTHER = "0x1111111111111111111111111111111111111111";

export const b64json = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64");

export function requirement({ amount = "10000", payTo = PAY_TO, network = NETWORK, asset = USDC_BASE, scheme = "exact" } = {}) {
  return { scheme, network, amount, asset, payTo, maxTimeoutSeconds: 300, extra: { name: "USD Coin", version: "2" } };
}

export function paymentRequired(accepts = [requirement()], { version = 2, error } = {}) {
  return b64json({ x402Version: version, accepts, ...(error ? { error } : {}) });
}

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

export function fakeGateway({ quote = paymentRequired(), paid, unpaid } = {}) {
  const requests = [];
  const fetch = async (input, init) => {
    const req = new Request(input, init);
    requests.push(req);
    const url = new URL(req.url);
    if (url.pathname === "/catalog") return json(200, { provider: "Agent Harbor", services: [] });
    if (req.headers.has("payment-signature")) {
      if (typeof paid === "function") return paid(req);
      if (paid) return paid;
      return json(200, { domain: url.searchParams.get("domain"), tier: "scrape" }, {
        "PAYMENT-RESPONSE": b64json({ success: true, transaction: "0xabc", network: NETWORK }),
        "X-Request-ID": "rid123",
      });
    }
    if (unpaid) return typeof unpaid === "function" ? unpaid(req) : unpaid;
    return json(402, {}, { "PAYMENT-REQUIRED": quote });
  };
  return { fetch, requests, json };
}

export function fakeX402() {
  const state = { signed: 0, registered: [], policies: [] };
  class x402Client {
    register(network, scheme) {
      state.registered.push({ network, scheme });
      return this;
    }
    registerPolicy(policy) {
      state.policies.push(policy);
      return this;
    }
  }
  class ExactEvmScheme {
    constructor(signer) {
      this.signer = signer;
    }
  }
  function wrapFetchWithPayment(fetch) {
    return async (input, init) => {
      const request = new Request(input, init);
      const res = await fetch(request.clone());
      if (res.status !== 402) return res;
      const required = JSON.parse(Buffer.from(res.headers.get("payment-required"), "base64").toString());
      let reqs = required.accepts;
      for (const p of state.policies) reqs = p(required.x402Version, reqs);
      if (!reqs.length) throw new Error("Failed to create payment payload: all requirements filtered out");
      state.signed += 1;
      const retry = request.clone();
      retry.headers.set("PAYMENT-SIGNATURE", b64json({ x402Version: 2, accepted: reqs[0], payload: { signature: "0xfake" } }));
      return fetch(retry);
    };
  }
  return { modules: { wrapFetchWithPayment, x402Client, ExactEvmScheme }, state };
}
