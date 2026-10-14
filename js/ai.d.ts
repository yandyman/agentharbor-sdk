import type { AgentHarborClient, ToolSpec } from "./index.js";

export const TOOL_SPECS: ReadonlyArray<ToolSpec>;
export const DOMAIN_DESCRIPTION: string;

/**
 * Vercel AI SDK tools (one per paid route), keyed by name:
 * agentharbor_company, agentharbor_scrape, agentharbor_ai_crawlers, agentharbor_enrich, agentharbor_audit.
 * Pass the result as `tools` to generateText / streamText.
 */
export function agentHarborTools(
  client: AgentHarborClient,
  options?: { include?: string[] },
): Record<string, import("ai").Tool<{ domain: string }, unknown>>;
