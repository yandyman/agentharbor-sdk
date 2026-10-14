// Typed errors. Every error carries `charged`: false when no payment can have settled,
// null when the client cannot know (OutcomeUnknown).

export class AgentHarborError extends Error {
  /** @param {string} message @param {{ cause?: unknown }} [options] */
  constructor(message, options) {
    super(message, options);
    this.name = new.target.name;
    /** @type {boolean | null} */
    this.charged = false;
  }
}

/** The domain is not a bare public hostname. Thrown before any request. */
export class InvalidDomain extends AgentHarborError {}

/** The client refused the 402 quote. Nothing was signed or sent. */
export class PaymentRefused extends AgentHarborError {
  /** @param {string} message @param {object | null} [quote] */
  constructor(message, quote = null) {
    super(message);
    this.quote = quote;
  }
}
/** The quoted amount exceeds maxPriceUsd. */
export class PriceTooHigh extends PaymentRefused {}
/** The quote pays an address other than the expected payTo. */
export class UnexpectedPayee extends PaymentRefused {}
/** The quote is not x402 v2 `exact` USDC on Base mainnet (eip155:8453). */
export class UnsupportedNetwork extends PaymentRefused {}
/** The 402 had no decodable x402 v2 PAYMENT-REQUIRED header. */
export class MalformedPaymentRequired extends PaymentRefused {}

/** The route is paid and no account was configured. `quote` holds the vetted price. */
export class WalletRequired extends AgentHarborError {
  /** @param {string} message @param {object | null} [quote] */
  constructor(message, quote = null) {
    super(message);
    this.quote = quote;
  }
}

/** A payment was built but not accepted (402 again, or the x402 library failed). Not charged. */
export class PaymentFailed extends AgentHarborError {}

/** No answer arrived and no payment had been sent (DNS, connection, timeout). */
export class RequestFailed extends AgentHarborError {}

/** The server answered 4xx/5xx. `detail` is the server's JSON detail (or text). */
export class APIError extends AgentHarborError {
  /** @param {string} message @param {number} status @param {unknown} detail */
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** The gateway answered 4xx/5xx. It settles only responses below 400, so this was not charged. */
export class NotCharged extends APIError {}

/** A signed payment was sent but no usable answer arrived. It may have been served and charged. */
export class OutcomeUnknown extends AgentHarborError {
  /** @param {string} message @param {{ cause?: unknown }} [options] */
  constructor(message, options) {
    super(message, options);
    this.charged = null;
  }
}
