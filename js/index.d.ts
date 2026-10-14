// Hand-written types for the `agentharbor` package (plain ESM JavaScript, no build step).

export const VERSION: string;
export const DEFAULT_BASE_URL: "https://x402.agentharbor.agency";
/** Agent Harbor's receiving address. */
export const PAY_TO: string;
/** Base mainnet (CAIP-2). */
export const NETWORK: "eip155:8453";
/** USDC on Base mainnet. */
export const USDC_BASE: string;
/** The gateway's domain regex (RE2/ECMA safe). */
export const DOMAIN_PATTERN: string;
/** List prices in USD by route path. */
export const PRICES_USD: Readonly<Record<"/company" | "/scrape" | "/ai-crawlers" | "/enrich" | "/audit", string>>;

export interface ToolSpec {
  readonly name: string;
  readonly method: "company" | "scrape" | "aiCrawlers" | "enrich" | "audit";
  readonly path: string;
  readonly priceUsd: string;
  readonly description: string;
}
export const TOOL_SPECS: ReadonlyArray<ToolSpec>;

/** A vetted payment requirement from a 402 challenge. */
export interface Quote {
  /** Atomic USDC units (6 decimals), as a decimal string. */
  amountAtomic: string;
  /** e.g. "0.01" */
  priceUsd: string;
  payTo: string;
  network: string;
  asset: string;
  scheme: string;
  requirement: Record<string, unknown>;
}

/** Decoded PAYMENT-RESPONSE settlement receipt. */
export interface PaymentReceipt {
  success?: boolean;
  transaction?: string;
  network?: string;
  payer?: string;
  [key: string]: unknown;
}

/** The JSON body of a served call, with non-enumerable payment metadata. */
export type AgentHarborResult<T = Record<string, any>> = T & {
  readonly payment: PaymentReceipt | null;
  readonly quote: Quote | null;
  readonly requestId: string | null;
};

/** Modules used to pay. Loaded lazily from @x402/fetch and @x402/evm unless supplied. */
export interface X402Modules {
  wrapFetchWithPayment: (fetch: typeof globalThis.fetch, client: any) => typeof globalThis.fetch;
  x402Client: new () => {
    register(network: string, scheme: unknown): unknown;
    registerPolicy(policy: (version: number, reqs: any[]) => any[]): unknown;
  };
  ExactEvmScheme: new (signer: any) => unknown;
}

export interface AgentHarborOptions {
  /** A viem account (e.g. privateKeyToAccount(...)) or any x402 ClientEvmSigner. */
  account?: { address: string; [key: string]: any };
  /** Hex private key; converted with viem's privateKeyToAccount on first paid call. */
  privateKey?: string;
  /** Default https://x402.agentharbor.agency */
  baseUrl?: string;
  /** The most one call may cost, in USD. A higher 402 quote is refused before signing. Default 0.05. */
  maxPriceUsd?: number | string;
  /** fetch implementation. Default globalThis.fetch. */
  fetch?: typeof globalThis.fetch;
  /** Per-request timeout in ms. Default 150000 (/enrich can take ~120 s). */
  timeoutMs?: number;
  /** The only address this client will pay. Default PAY_TO. */
  payTo?: string;
  /** Default "eip155:8453". */
  network?: string;
  /** Default USDC_BASE. */
  asset?: string;
  /** Advanced: supply the x402 modules instead of the lazy dynamic import. */
  x402?: X402Modules;
}

export interface CallOptions {
  /** Per-call budget, overriding the client's maxPriceUsd. */
  maxPriceUsd?: number | string;
}

export interface AgentHarborClient {
  readonly baseUrl: string;
  readonly maxPriceUsd: number | string;
  /** The paying wallet's address, once known. */
  readonly address: string | null;
  /** $0.005: business name with source, generic role email if published, up to 10 platform names. */
  company(domain: string, options?: CallOptions): Promise<AgentHarborResult>;
  /** $0.01: business name, contact surface, technology platforms with evidence. */
  scrape(domain: string, options?: CallOptions): Promise<AgentHarborResult>;
  /** $0.01: AI-crawler access per robots.txt, llms.txt, sitemaps, page-level robots. */
  aiCrawlers(domain: string, options?: CallOptions): Promise<AgentHarborResult>;
  /** $0.05: validated company profile (firmographics + tech-stack summary). */
  enrich(domain: string, options?: CallOptions): Promise<AgentHarborResult>;
  /** $0.05: home-page audit (tags, consent, schema, AI crawlers, SEO) as a ranked fix list. */
  audit(domain: string, options?: CallOptions): Promise<AgentHarborResult>;
  /** Free: services, prices, network and payment address. */
  catalog(): Promise<Record<string, any>>;
}

export function createAgentHarbor(options?: AgentHarborOptions): AgentHarborClient;

export function validateDomain(value: unknown): string;
export function usdToAtomic(usd: number | string): bigint;
export function decodePaymentRequired(header: string | null | undefined): Record<string, any>;
export function decodePaymentResponse(header: string | null | undefined): PaymentReceipt | null;
export interface GuardOptions {
  maxPriceUsd: number | string;
  payTo?: string;
  network?: string;
  asset?: string;
}
/** Vet a base64 PAYMENT-REQUIRED header; returns the first acceptable quote or throws a PaymentRefused. */
export function checkPaymentRequired(header: string | null | undefined, options: GuardOptions): Quote;
/** An x402 PaymentPolicy applying the same check. */
export function makePolicy(options: GuardOptions): (version: number, reqs: any[]) => any[];

export class AgentHarborError extends Error {
  /** false: not charged. null: unknown (see OutcomeUnknown). */
  charged: boolean | null;
}
export class InvalidDomain extends AgentHarborError {}
export class PaymentRefused extends AgentHarborError {
  quote: Record<string, unknown> | null;
}
export class PriceTooHigh extends PaymentRefused {}
export class UnexpectedPayee extends PaymentRefused {}
export class UnsupportedNetwork extends PaymentRefused {}
export class MalformedPaymentRequired extends PaymentRefused {}
export class WalletRequired extends AgentHarborError {
  quote: Quote | null;
}
export class PaymentFailed extends AgentHarborError {}
export class RequestFailed extends AgentHarborError {}
export class APIError extends AgentHarborError {
  status: number;
  detail: unknown;
}
export class NotCharged extends APIError {}
export class OutcomeUnknown extends AgentHarborError {}
