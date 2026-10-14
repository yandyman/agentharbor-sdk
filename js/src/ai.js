// Vercel AI SDK tools. Importing "agentharbor/ai" loads the `ai` and `zod` peer dependencies;
// the main "agentharbor" entry never does.
import { tool } from "ai";
import { z } from "zod";
import { buildTools } from "./tools.js";

export { TOOL_SPECS, DOMAIN_DESCRIPTION } from "./tools.js";

/**
 * One AI SDK tool per paid route, keyed by tool name (agentharbor_company, ...).
 * @param {import("../index.d.ts").AgentHarborClient} client
 * @param {{ include?: string[] }} [options] keep only these tool names or method names
 */
export function agentHarborTools(client, options) {
  return buildTools(client, { tool, z }, options);
}
