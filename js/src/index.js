// Client for Agent Harbor's pay-per-call x402 API (USDC on Base).
//
// Every paid call: the request goes out unpaid; the gateway answers 402 with a base64 JSON
// PAYMENT-REQUIRED header; the guard fetch below decodes and vets it (price cap, payee,
// network/asset) and throws on a bad quote, before the x402 paying fetch can sign. Only then
// does @x402/fetch sign a USDC authorization and retry. The gateway settles only responses
// below 400, so a 4xx/5xx answer is not charged.
import { validateDomain } from "./domain.js";
import {
  AgentHarborError,
  APIError,
  NotCharged,
  OutcomeUnknown,
  PaymentFailed,
  PaymentRefused,
  RequestFailed,
  WalletRequired,
} from "./errors.js";
import {
  NETWORK,
  PAY_TO,
  USDC_BASE,
  checkPaymentRequired,
  decodePaymentRequired,
  decodePaymentResponse,
  makePolicy,
  usdToAtomic,
} from "./guard.js";

export * from "./errors.js";
export { validateDomain, DOMAIN_PATTERN } from "./domain.js";
export {
  PAY_TO, NETWORK, USDC_BASE, checkPaymentRequired, makePolicy, usdToAtomic,
  decodePaymentRequired, decodePaymentResponse,
} from "./guard.js";
export { TOOL_SPECS, PRICES_USD } from "./tools.js";

export const VERSION = "0.1.0";
export const DEFAULT_BASE_URL = "https://x402.agentharbor.agency";
const CLOUDFLARE_TIMEOUTS = new Set([520, 521, 522, 523, 524, 525, 526, 527]);

/** Load the x402 v2 fetch wrapper and EVM scheme on first paid call. */
async function loadX402() {
  try {
    const [fetchMod, evmMod] = await Promise.all([
      import("@x402/fetch"),
      import("@x402/evm/exact/client"),
    ]);
    return {
      wrapFetchWithPayment: fetchMod.wrapFetchWithPayment,
      x402Client: fetchMod.x402Client,
      ExactEvmScheme: evmMod.ExactEvmScheme,
    };
  } catch (e) {
    throw new AgentHarborError("Paying needs the x402 peer dependencies: npm install @x402/fetch @x402/evm viem",
      { cause: e });
  }
}

/** @param {string} privateKey */
async function accountFromKey(privateKey) {
  let mod;
  try {
    mod = await import("viem/accounts");
  } catch (e) {
    throw new AgentHarborError("privateKey needs viem: npm install viem", { cause: e });
  }
  try {
    return mod.privateKeyToAccount(/** @type {`0x${string}`} */ (privateKey));
  } catch {
    // no cause: never let the key (or a message quoting it) reach a log
    throw new TypeError("privateKey is not a valid EVM private key");
  }
}

/** @param {unknown} detail */
const saysNotCharged = (detail) =>
  !!detail && typeof detail === "object" && /** @type {any} */ (detail).charged === false;

/** @param {Response} res @param {string} text */
function detailOf(res, text) {
  try {
    const body = JSON.parse(text);
    return body && typeof body === "object" && "detail" in body ? body.detail : body;
  } catch {
    return text.slice(0, 500);
  }
}

/** @param {unknown} d */
const short = (d) => (typeof d === "string" ? d : JSON.stringify(d)).slice(0, 300);

/**
 * Attach payment metadata as non-enumerable properties (JSON.stringify shows only the body).
 * @param {any} body @param {object} meta
 */
function withMeta(body, meta) {
  const out = body && typeof body === "object" && !Array.isArray(body) ? body : { data: body };
  for (const [k, v] of Object.entries(meta)) {
    Object.defineProperty(out, k, { value: v, enumerable: false });
  }
  return out;
}

/**
 * Create a client. See index.d.ts for the full option list.
 * @param {import("../index.d.ts").AgentHarborOptions} [options]
 * @returns {import("../index.d.ts").AgentHarborClient}
 */
export function createAgentHarbor(options = {}) {
  const {
    account,
    privateKey,
    baseUrl = DEFAULT_BASE_URL,
    maxPriceUsd = 0.05,
    fetch: baseFetch = globalThis.fetch,
    timeoutMs = 150_000,
    payTo = PAY_TO,
    network = NETWORK,
    asset = USDC_BASE,
    x402,
  } = options;
  if (account && privateKey) throw new TypeError("pass account or privateKey, not both");
  if (typeof baseFetch !== "function") throw new TypeError("no fetch available; pass options.fetch");
  usdToAtomic(maxPriceUsd);
  const base = String(baseUrl).replace(/\/+$/, "");
  /** @type {any} */
  let acct = account || null;
  /** @type {string | undefined} */
  let pendingKey = privateKey;
  const headers = { Accept: "application/json", "User-Agent": `agentharbor-js/${VERSION}` };

  async function getAccount() {
    if (!acct && pendingKey) {
      acct = await accountFromKey(pendingKey);
      pendingKey = undefined;
    }
    return acct;
  }

  /**
   * @param {string} path @param {string} domain @param {{ maxPriceUsd?: number | string }} [callOpts]
   */
  async function paidGet(path, domain, callOpts = {}) {
    const d = validateDomain(domain);
    const cap = callOpts.maxPriceUsd ?? maxPriceUsd;
    usdToAtomic(cap);
    const state = {
      quote: /** @type {any} */ (null),
      unpaidStatus: /** @type {number|null} */ (null),
      paidSent: false,
      paidStatus: /** @type {number|null} */ (null),
    };

    /** Sits under the paying fetch: vets every unpaid 402 before x402 can sign. */
    const guardedFetch = async (/** @type {any} */ input, /** @type {any} */ init) => {
      const req = new Request(input, init);
      const paid = req.headers.has("payment-signature") || req.headers.has("x-payment");
      if (paid) state.paidSent = true;
      const res = await baseFetch(req);
      if (paid) {
        state.paidStatus = res.status;
        return res;
      }
      state.unpaidStatus = res.status;
      if (res.status === 402) {
        state.quote = checkPaymentRequired(res.headers.get("payment-required"),
          { maxPriceUsd: cap, payTo, network, asset });
      }
      return res;
    };

    const wallet = await getAccount();
    /** @type {(input: any, init?: any) => Promise<Response>} */
    let doFetch = guardedFetch;
    if (wallet) {
      const mods = x402 || (await loadX402());
      const client = new mods.x402Client();
      client.register(network, new mods.ExactEvmScheme(wallet)); // Base mainnet only
      client.registerPolicy(makePolicy({ maxPriceUsd: cap, payTo, network, asset }));
      doFetch = mods.wrapFetchWithPayment(guardedFetch, client);
    }

    const url = `${base}${path}?domain=${encodeURIComponent(d)}`;
    let res;
    let text;
    try {
      res = await doFetch(url, { method: "GET", headers, signal: AbortSignal.timeout(timeoutMs) });
      text = await res.text();
    } catch (e) {
      throw mapException(path, state, e, !!wallet);
    }
    return mapResponse(path, state, res, text);
  }

  /**
   * @param {string} path @param {any} state @param {any} e @param {boolean} hasWallet
   * @returns {AgentHarborError}
   */
  function mapException(path, state, e, hasWallet) {
    for (let c = e, i = 0; c && i < 10; c = c.cause, i++) {
      if (c instanceof PaymentRefused) return c; // a refusal wrapped by x402 is still a refusal
    }
    if (e instanceof AgentHarborError) return e;
    if (state.paidSent && (state.paidStatus === null || state.paidStatus < 400)) {
      return new OutcomeUnknown(
        `GET ${path}: a signed payment was sent but no usable answer arrived (${e?.name || "Error"}). ` +
        `The call may have been served and charged; check ${acct?.address || "the payer"} on basescan.org before retrying.`,
        { cause: e });
    }
    if (state.unpaidStatus === null) {
      // no answer at all yet: DNS, connection or timeout, and nothing was signed
      return new RequestFailed(`GET ${path} failed before any payment: ${e?.message}`, { cause: e });
    }
    if (hasWallet && !state.paidSent) {
      return new PaymentFailed(`GET ${path}: the x402 payment could not be built: ${e?.message}; not charged`, { cause: e });
    }
    return new RequestFailed(`GET ${path} failed: ${e?.message}`, { cause: e });
  }

  /** @param {string} path @param {any} state @param {Response} res @param {string} text */
  function mapResponse(path, state, res, text) {
    const status = res.status;
    if (status < 400) {
      let body;
      try {
        body = JSON.parse(text);
      } catch {
        const err = new APIError(`GET ${path} answered ${status} with a non-JSON body`, status, text.slice(0, 500));
        err.charged = state.paidSent;
        throw err;
      }
      return withMeta(body, {
        payment: decodePaymentResponse(res.headers.get("payment-response") || res.headers.get("x-payment-response")),
        quote: state.quote,
        requestId: res.headers.get("x-request-id"),
      });
    }
    if (status === 402) {
      if (!state.paidSent) {
        throw new WalletRequired(
          `GET ${path} costs $${state.quote?.priceUsd ?? "?"} USDC on Base; configure a wallet ` +
          "(account or privateKey, with npm install @x402/fetch @x402/evm viem)", state.quote);
      }
      let reason = null;
      try {
        reason = decodePaymentRequired(res.headers.get("payment-required")).error ?? null;
      } catch { /* no reason available */ }
      throw new PaymentFailed(`GET ${path}: the gateway rejected the payment${reason ? ` (${reason})` : ""}; not charged`);
    }
    const detail = detailOf(res, text);
    if (status >= 500 && state.paidSent && !saysNotCharged(detail) &&
        (CLOUDFLARE_TIMEOUTS.has(status) || typeof detail !== "object" || detail === null)) {
      throw new OutcomeUnknown(
        `GET ${path}: HTTP ${status} after a signed payment, and not from the gateway itself. ` +
        "The call may have been served and charged; check the payer on basescan.org before retrying.");
    }
    throw new NotCharged(`GET ${path} answered ${status}; not charged: ${short(detail)}`, status, detail);
  }

  async function catalog() {
    let res;
    let text;
    try {
      res = await baseFetch(`${base}/catalog`, { headers, signal: AbortSignal.timeout(timeoutMs) });
      text = await res.text();
    } catch (e) {
      throw new RequestFailed(`GET /catalog failed: ${/** @type {any} */ (e)?.message}`, { cause: e });
    }
    if (res.status >= 400) throw new NotCharged(`GET /catalog answered ${res.status}`, res.status, detailOf(res, text));
    return JSON.parse(text);
  }

  return Object.freeze({
    baseUrl: base,
    maxPriceUsd,
    get address() {
      return acct?.address ?? null;
    },
    company: (/** @type {string} */ domain, /** @type {any} */ o) => paidGet("/company", domain, o),
    scrape: (/** @type {string} */ domain, /** @type {any} */ o) => paidGet("/scrape", domain, o),
    aiCrawlers: (/** @type {string} */ domain, /** @type {any} */ o) => paidGet("/ai-crawlers", domain, o),
    enrich: (/** @type {string} */ domain, /** @type {any} */ o) => paidGet("/enrich", domain, o),
    audit: (/** @type {string} */ domain, /** @type {any} */ o) => paidGet("/audit", domain, o),
    catalog,
    toJSON: () => ({ baseUrl: base, maxPriceUsd, address: acct?.address ?? null }),
  });
}
