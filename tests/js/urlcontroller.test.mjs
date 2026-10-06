// URL controller with injected fake location/history: a headless simulation of the browser. node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const load = (f) => import(path.join(here, "..", "..", "codegraph", "vis", "static", f));
const { parseHash } = await load("state.js");
const { createUrlController, replayStubs, MAX_EXPANDED } = await load("urlstate.js");

function fakeBrowser(hash = "") {
  const entries = [hash];
  let i = 0;
  const b = {
    hashchanges: 0,
    location: {
      get hash() { return entries[i]; },
      set hash(h) { // like the browser: a new entry, then hashchange
        const v = h === "#" ? "" : h;
        if (v === entries[i]) return;
        entries.splice(i + 1); entries.push(v); i++; b.fire();
      },
    },
    history: { replaceState: (_s, _t, url) => { entries[i] = url.startsWith("#") ? url : ""; } },
    back() { i--; b.fire(); },
    fire() { b.hashchanges++; if (b.onhash) b.onhash(); },
    get length() { return entries.length; },
  };
  return b;
}

function setup(hash = "") {
  const b = fakeBrowser(hash);
  const renders = [], notices = [];
  const ctl = createUrlController({ location: b.location, history: b.history,
    render: (refetch) => renders.push(refetch), notice: (n) => notices.push(n) });
  b.onhash = () => ctl.onHashChange();
  return { b, ctl, renders, notices };
}

test("empty hash is the overview landing state", () => {
  const { ctl } = setup("");
  assert.equal(ctl.state.view, "overview");
  assert.equal(ctl.state.focus, null);
});

test("Back steps through focus, mode and group-by changes only", () => {
  const { b, ctl } = setup("#focus=A");
  ctl.apply({ depth: 3 });                      // replace
  ctl.apply({ stubs: ["stub:A:out:calls"] });   // replace
  ctl.apply({ filters: { hiddenNodeKinds: ["file"], hiddenEdgeKinds: [] } }); // replace
  ctl.apply({ mode: "impact" });                // push
  ctl.apply({ focus: "B" });                    // push
  ctl.apply({ limit: 300 });                    // replace
  assert.equal(b.length, 3);
  b.back();
  assert.equal(ctl.state.focus, "A");
  assert.equal(ctl.state.mode, "impact");
  assert.equal(ctl.state.depth, 3);
  assert.deepEqual(ctl.state.filters.hiddenNodeKinds, ["file"]);
  b.back();
  assert.equal(ctl.state.mode, "neighborhood");
  assert.equal(ctl.state.depth, 3);
});

test("replace changes render themselves; pushes render via hashchange, once", () => {
  const { b, ctl, renders } = setup("#focus=A");
  ctl.apply({ depth: 3 });
  assert.deepEqual(renders, [true]);
  ctl.apply({ stubs: ["s"] });
  assert.deepEqual(renders, [true]); // stub expansions are already on screen
  ctl.apply({ focus: "B" });
  assert.equal(b.hashchanges, 1);
  assert.deepEqual(renders, [true, true]);
});

test("over-long expanded lists are truncated with a notice, in the URL too", () => {
  const ids = Array.from({ length: 60 }, (_, i) => "g" + i);
  const { b, ctl, notices } = setup("");
  ctl.apply({ expanded: ids });
  assert.equal(ctl.state.expanded.length, MAX_EXPANDED);
  assert.equal(parseHash(b.location.hash).expanded.length, MAX_EXPANDED);
  assert.match(notices.at(-1), /state truncated/i);
  const loaded = setup("#" + new URLSearchParams(ids.map((x) => ["expanded", x])).toString());
  assert.equal(loaded.ctl.state.expanded.length, MAX_EXPANDED);
  assert.match(loaded.notices.at(-1), /state truncated/i);
});

test("replayStubs re-expands recorded stubs in order and reports the ones replayed", async () => {
  const model = {
    stubs: [{ id: "s1", owner: "a" }], log: [],
    view() { return { stubs: this.stubs }; },
    expand(id, page) { this.stubs = page.next ? [{ id: "s1", owner: "a" }] : []; this.log.push([id, page.n]); },
  };
  let n = 0;
  const done = await replayStubs(model, ["s1", "s1", "gone"], async () => ({ n: ++n, next: n < 2 }), () => true);
  assert.deepEqual(model.log, [["s1", 1], ["s1", 2]]);
  assert.deepEqual(done, ["s1", "s1"]); // stale ids are dropped
});

test("replayStubs stops when superseded by a newer render", async () => {
  const model = { n: 0, view: () => ({ stubs: [{ id: "s1", owner: "a" }] }), expand() { model.n++; } };
  await replayStubs(model, ["s1", "s1"], async () => ({}), () => false);
  assert.equal(model.n, 0);
});
