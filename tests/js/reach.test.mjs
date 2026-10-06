// Unit tests for the impact/dependencies UI helpers. Run:  node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const staticDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "codegraph", "vis", "static");
const load = (f) => import(path.join(staticDir, f));

const { parseHash, formatHash, DEFAULTS, ALL_DEPTH } = await load("state.js");
const { fetchNeighborhood } = await load("api.js");
const { depthOptions, ringText } = await load("reach.js");

test("mode defaults to both and round-trips through the hash", () => {
  assert.equal(DEFAULTS.mode, "both");
  assert.equal(formatHash({ focus: "x", ...DEFAULTS }), "#focus=x");
  const s = { ...DEFAULTS, focus: "x", mode: "impact", depth: 3 };
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.equal(parseHash("#mode=bogus").mode, "both");
});

test("depth 'all' maps to the server maximum and round-trips", () => {
  assert.equal(ALL_DEPTH, 10);
  assert.equal(parseHash("#depth=all").depth, ALL_DEPTH);
  assert.equal(formatHash({ ...DEFAULTS, focus: "x", depth: ALL_DEPTH }), "#focus=x&depth=all");
  assert.equal(parseHash("#depth=7").depth, DEFAULTS.depth);
});

test("depth options are 1-5 then all", () => {
  assert.deepEqual(depthOptions().map((o) => o.label), ["1", "2", "3", "4", "5", "all"]);
  assert.equal(depthOptions().at(-1).value, ALL_DEPTH);
});

test("ringText lists per-ring counts up to the depth, zero-filling", () => {
  assert.equal(ringText({ 1: 3, 2: 12 }, 3), "1: 3 · 2: 12 · 3: 0");
  assert.equal(ringText({ 1: 3, 2: 12 }, 10), "1: 3 · 2: 12");
  assert.equal(ringText(null, 2), "");
});

test("fetchNeighborhood sends mode", async () => {
  let seen;
  await fetchNeighborhood("a", { depth: 10, mode: "impact" }, async (u) => { seen = u; return { status: 404 }; });
  assert.equal(seen, "/api/neighborhood/a?depth=10&mode=impact");
});
