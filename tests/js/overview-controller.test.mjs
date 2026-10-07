// Overview controller with fakes for the DOM and cytoscape: a headless simulation of clicking nodes. node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { createOverviewController } = await import(path.join(here, "..", "..", "codegraph", "vis", "static", "overview-controller.js"));

function setup({ nodes, details = {} }) {
  const els = new Map();
  const $ = (id) => {
    if (!els.has(id)) els.set(id, { textContent: "", disabled: false, value: "", checked: false, addEventListener() {}, replaceChildren() {}, append() {} });
    return els.get(id);
  };
  const canvas = { cy: {
    on() {},
    getElementById: (id) => ({ length: id in nodes ? 1 : 0, data: () => nodes[id], select() {} }),
  } };
  const panel = []; // every renderPanel call: the detail it was given
  const ctl = createOverviewController({
    $, canvas, overview: { show() {} }, url: { state: { expanded: [], groupBy: "directory", externals: false, okinds: null } },
    setState() {}, isCurrent: () => true, onError() {},
    fetchOverview: async () => ({ available_kinds: [], kinds: [] }),
    fetchNode: async (id) => details[id] ?? null,
    renderPanel: (_root, detail) => panel.push(detail),
  });
  return { ctl, panel };
}

const tick = () => new Promise((r) => setImmediate(r));

test("clicking a node shows its details in the panel", async () => {
  const detail = { qualified_name: "Circle::area", kind: "function" };
  const { ctl, panel } = setup({ nodes: { a: { id: "a", nodeId: "n1", full: "Circle::area" } }, details: { n1: detail } });
  ctl.tap("a");
  await tick();
  assert.equal(panel.at(-1), detail);
});

test("a late response for a previous click does not overwrite the panel", async () => {
  const d1 = { qualified_name: "one" }, d2 = { qualified_name: "two" };
  const { ctl, panel } = setup({
    nodes: { a: { id: "a", nodeId: "n1", full: "one" }, b: { id: "b", nodeId: "n2", full: "two" } },
    details: { n1: d1, n2: d2 },
  });
  ctl.tap("a"); ctl.tap("b");
  await tick();
  assert.equal(panel.at(-1), d2);
  assert.ok(!panel.includes(d1));
});

test("re-rendering keeps the selected node's details; deselecting clears them", async () => {
  const detail = { qualified_name: "x" };
  const { ctl, panel } = setup({ nodes: { a: { id: "a", nodeId: "n1", full: "x" } }, details: { n1: detail } });
  ctl.tap("a");
  await tick();
  await ctl.render(1);
  assert.equal(panel.at(-1), detail);
  ctl.select(null);
  assert.equal(panel.at(-1), null);
});

test("selectedNodeId is the selected node, and null for a Group or no selection", () => {
  const { ctl } = setup({ nodes: { a: { id: "a", nodeId: "n1", full: "x" }, g: { id: "g", full: "dir" } } });
  assert.equal(ctl.selectedNodeId(), null);
  ctl.tap("a");
  assert.equal(ctl.selectedNodeId(), "n1");
  ctl.tap("g");
  assert.equal(ctl.selectedNodeId(), null);
});
