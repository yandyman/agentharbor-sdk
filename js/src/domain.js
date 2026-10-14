// Client-side copy of the gateway's domain check (x402_gateway/domain.py + DOMAIN_PATTERN).
import { InvalidDomain } from "./errors.js";

/** Same expression the gateway publishes in its OpenAPI/Bazaar input schema. */
export const DOMAIN_PATTERN =
  "^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$";
const DOMAIN_RE = new RegExp(DOMAIN_PATTERN);
const LABEL_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const BLOCKED_TLDS = new Set([
  "localhost", "local", "localdomain", "internal", "intranet", "lan", "home", "corp",
  "private", "invalid", "arpa", "onion",
]);

/**
 * Return the normalised (lower-case, no trailing dot) domain or throw InvalidDomain.
 * @param {unknown} value
 * @returns {string}
 */
export function validateDomain(value) {
  if (typeof value !== "string") throw new InvalidDomain("domain must be a string");
  let d = value.trim().toLowerCase();
  if (d.endsWith(".")) d = d.slice(0, -1);
  if (!d || d.length > 253) throw new InvalidDomain("domain is empty or too long");
  // eslint-disable-next-line no-control-regex
  if (!/^[\x00-\x7f]*$/.test(d) || /[\s/\\:@?#[\]%]/.test(d)) {
    throw new InvalidDomain(`${JSON.stringify(value)} must be a bare hostname such as example.com (no scheme, port or path)`);
  }
  const labels = d.split(".");
  if (labels.length < 2 || !labels.every((l) => LABEL_RE.test(l)) || !DOMAIN_RE.test(d)) {
    throw new InvalidDomain(`${JSON.stringify(value)} is not a valid hostname`);
  }
  const tld = labels[labels.length - 1];
  if (!/[a-z]/.test(tld) || BLOCKED_TLDS.has(tld)) {
    throw new InvalidDomain(`${JSON.stringify(value)} is not a public hostname`);
  }
  if (!/^[a-z]+$/.test(tld) && !tld.startsWith("xn--")) {
    throw new InvalidDomain(`${JSON.stringify(value)} does not end in a valid top-level domain`);
  }
  return d;
}
