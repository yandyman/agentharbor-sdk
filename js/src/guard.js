// The buyer-side budget guard: pure functions, no network, no x402 library.
// The client decodes the 402 PAYMENT-REQUIRED header and runs checkPaymentRequired on it
// before the paying fetch can sign anything. makePolicy registers the same check inside x402.
import {
  MalformedPaymentRequired,
  PaymentRefused,
  PriceTooHigh,
  UnexpectedPayee,
  UnsupportedNetwork,
} from "./errors.js";

/** Agent Harbor's receiving address (published in /catalog, /.well-known/x402 and every 402). */
export const PAY_TO = "0x840C829530DF7B4CCF700Fa3A0060cF2C80b014e";
/** Base mainnet, CAIP-2. */
export const NETWORK = "eip155:8453";
/** USDC on Base mainnet. */
export const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
export const X402_VERSION = 2;
export const SCHEME = "exact";
const SCALE = 1_000_000n;

/**
 * USD budget to USDC atomic units (6 decimals), rounded down.
 * @param {number | string} usd
 * @returns {bigint}
 */
export function usdToAtomic(usd) {
  const s = typeof usd === "number" ? (Number.isFinite(usd) ? usd.toFixed(12) : "x") : String(usd).trim();
  const m = /^(\d+)(?:\.(\d*))?$/.exec(s);
  if (!m) throw new TypeError(`invalid non-negative USD amount: ${String(usd)}`);
  const frac = (m[2] || "").padEnd(6, "0").slice(0, 6);
  return BigInt(m[1]) * SCALE + BigInt(frac);
}

/** @param {bigint} atomic @returns {string} e.g. 10000n -> "0.01" */
export function formatUsd(atomic) {
  const whole = atomic / SCALE;
  const frac = (atomic % SCALE).toString().padStart(6, "0").replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : `${whole}`;
}

/** @param {string} s */
function b64json(s) {
  const bin = atob(s.trim());
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

/**
 * Decode a base64 JSON PAYMENT-REQUIRED header.
 * @param {string | null | undefined} header
 * @returns {Record<string, any>}
 */
export function decodePaymentRequired(header) {
  if (!header) throw new MalformedPaymentRequired("402 without a PAYMENT-REQUIRED header; refusing to pay");
  let data;
  try {
    data = b64json(header);
  } catch {
    throw new MalformedPaymentRequired("PAYMENT-REQUIRED header is not base64 JSON; refusing to pay");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new MalformedPaymentRequired("PAYMENT-REQUIRED header is not a JSON object; refusing to pay");
  }
  return data;
}

/**
 * Decode the PAYMENT-RESPONSE settlement receipt, or null.
 * @param {string | null | undefined} header
 */
export function decodePaymentResponse(header) {
  if (!header) return null;
  try {
    const d = b64json(header);
    return d && typeof d === "object" ? d : null;
  } catch {
    return null;
  }
}

/**
 * Vet one payment requirement. Returns a quote or throws a PaymentRefused subclass.
 * @param {Record<string, any>} req
 * @param {{ maxAtomic: bigint, payTo?: string, network?: string, asset?: string }} o
 */
export function evaluateRequirement(req, { maxAtomic, payTo = PAY_TO, network = NETWORK, asset = USDC_BASE }) {
  const r = req && typeof req === "object" ? req : {};
  const reqPayTo = r.payTo ?? r.pay_to;
  const amount = r.amount ?? r.maxAmountRequired;
  if (r.scheme !== SCHEME || r.network !== network || typeof r.asset !== "string" ||
      r.asset.toLowerCase() !== asset.toLowerCase()) {
    throw new UnsupportedNetwork(
      `quote is scheme=${r.scheme} network=${r.network} asset=${r.asset}; ` +
      `only ${SCHEME} USDC on ${network} (${asset}) is accepted`, r);
  }
  if (typeof reqPayTo !== "string" || reqPayTo.toLowerCase() !== payTo.toLowerCase()) {
    throw new UnexpectedPayee(`quote pays ${reqPayTo}, expected ${payTo}; refusing to pay`, r);
  }
  if (!/^\d+$/.test(String(amount ?? ""))) {
    throw new MalformedPaymentRequired(`quote amount ${amount} is not an atomic integer`, r);
  }
  const amountAtomic = BigInt(String(amount));
  if (amountAtomic > maxAtomic) {
    throw new PriceTooHigh(
      `quoted $${formatUsd(amountAtomic)} exceeds maxPriceUsd $${formatUsd(maxAtomic)}; refusing to pay`, r);
  }
  return {
    amountAtomic: amountAtomic.toString(), priceUsd: formatUsd(amountAtomic), payTo: reqPayTo,
    network: r.network, asset: r.asset, scheme: r.scheme, requirement: r,
  };
}

const REFUSAL_ORDER = [PriceTooHigh, UnexpectedPayee, UnsupportedNetwork, MalformedPaymentRequired];

/**
 * Vet a 402 challenge before paying. Returns the first acceptable requirement as a quote,
 * or throws PriceTooHigh / UnexpectedPayee / UnsupportedNetwork / MalformedPaymentRequired.
 * @param {string | null | undefined} header base64 PAYMENT-REQUIRED header value
 * @param {{ maxPriceUsd: number | string, payTo?: string, network?: string, asset?: string }} o
 */
export function checkPaymentRequired(header, { maxPriceUsd, payTo = PAY_TO, network = NETWORK, asset = USDC_BASE }) {
  const maxAtomic = usdToAtomic(maxPriceUsd);
  const data = decodePaymentRequired(header);
  if (data.x402Version !== X402_VERSION) {
    throw new UnsupportedNetwork(`x402Version ${data.x402Version} is not supported (need 2)`);
  }
  if (!Array.isArray(data.accepts) || data.accepts.length === 0) {
    throw new MalformedPaymentRequired("PAYMENT-REQUIRED has no accepts[]; refusing to pay");
  }
  /** @type {PaymentRefused[]} */
  const errors = [];
  for (const req of data.accepts) {
    try {
      return evaluateRequirement(req, { maxAtomic, payTo, network, asset });
    } catch (e) {
      if (!(e instanceof PaymentRefused)) throw e;
      errors.push(e);
    }
  }
  for (const cls of REFUSAL_ORDER) {
    const hit = errors.find((e) => e.constructor === cls);
    if (hit) throw hit;
  }
  throw errors[0];
}

/**
 * An x402 PaymentPolicy keeping only requirements that pass the same check (v2 only).
 * @param {{ maxPriceUsd: number | string, payTo?: string, network?: string, asset?: string }} o
 * @returns {(version: number, reqs: any[]) => any[]}
 */
export function makePolicy({ maxPriceUsd, payTo = PAY_TO, network = NETWORK, asset = USDC_BASE }) {
  const maxAtomic = usdToAtomic(maxPriceUsd);
  return (version, reqs) => {
    if (version !== X402_VERSION) return [];
    return reqs.filter((r) => {
      try {
        evaluateRequirement(r, { maxAtomic, payTo, network, asset });
        return true;
      } catch {
        return false;
      }
    });
  };
}
