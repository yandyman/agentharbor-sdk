import assert from "node:assert/strict";
import { test } from "node:test";

import { PRICES_USD, TOOL_SPECS, createAgentHarbor } from "../src/index.js";
import { buildTools } from "../src/tools.js";
import { ACCOUNT, fakeGateway, fakeX402 } from "./helpers.js";

test("prices match the gateway", () => {
  assert.deepEqual({ ...PRICES_USD },
    { "/company": "0.005", "/scrape": "0.01", "/ai-crawlers": "0.01", "/enrich": "0.05", "/audit": "0.05" });
});

test("descriptions are honest about price and charging", () => {
  for (const s of TOOL_SPECS) {
    assert.ok(s.description.includes(`$${s.priceUsd}.`), s.name);
    assert.ok(s.description.includes("not charged") && s.description.includes("USDC on Base"), s.name);
    assert.ok(s.description.length < 1024);
  }
  const withScan = TOOL_SPECS.filter((s) => s.description.includes("content_safety")).map((s) => s.path).sort();
  assert.deepEqual(withScan, ["/company", "/enrich", "/scrape"]);
});

// Stand-ins for `tool` from "ai" and `z` from "zod" (the real ones are peer dependencies).
const fakeTool = (def) => ({ ...def, __tool: true });
const fakeZ = {
  string: () => ({ type: "string", describe(d) { return { ...this, description: d }; } }),
  object: (shape) => ({ type: "object", shape }),
};

test("buildTools builds AI SDK tool definitions with inputSchema", async () => {
  const gw = fakeGateway();
  const x = fakeX402();
  const client = createAgentHarbor({ baseUrl: "https://gw.test", fetch: gw.fetch, account: ACCOUNT, x402: x.modules });
  const tools = buildTools(client, { tool: fakeTool, z: fakeZ });
  assert.deepEqual(Object.keys(tools), TOOL_SPECS.map((s) => s.name));
  const t = tools.agentharbor_scrape;
  assert.ok(t.__tool && t.inputSchema.type === "object" && t.inputSchema.shape.domain.type === "string");
  assert.match(t.inputSchema.shape.domain.description, /example\.com/);
  assert.equal((await t.execute({ domain: "example.com" })).domain, "example.com");
  const err = await t.execute({ domain: "http://bad" });
  assert.deepEqual([err.error, err.charged], ["InvalidDomain", false]);
  assert.deepEqual(Object.keys(buildTools(client, { tool: fakeTool, z: fakeZ }, { include: ["company", "agentharbor_audit"] })),
    ["agentharbor_company", "agentharbor_audit"]);
});

test("Python and JS tool specs share names and prices", async () => {
  const fs = await import("node:fs");
  const py = fs.readFileSync(new URL("../../python/src/agentharbor/_tools.py", import.meta.url), "utf8");
  // cheap cross-check: every price and name appears in the Python source
  for (const s of TOOL_SPECS) {
    assert.ok(py.includes(`"${s.name}"`) && py.includes(`"${s.priceUsd}"`), s.name);
  }
});
