// URL view-state policy. Pure (no DOM): what a change does to history and rendering, the cap on
// list-valued keys, and the user-facing messages. main.js only applies the results.
import { DEFAULTS, derivedView, formatHash, parseHash } from "./state.js";

export const MAX_EXPANDED = 50; // cap on `expanded` ids and on `stubs` expansions kept in the URL

// Changes that are navigation: Back steps through exactly these. Everything else replaces the entry.
const PUSH_KEYS = ["focus", "view", "mode", "groupBy"];
// Changes that need new data from the server; filters and stub expansions only touch what is on screen.
const REFETCH_KEYS = ["focus", "view", "depth", "direction", "kinds", "mode", "limit", "groupBy", "expanded", "okinds", "externals"];
// Changes that reload the focus neighborhood, invalidating stub expansions (their pages depend on it).
const RESET_STUB_KEYS = ["focus", "view", "depth", "direction", "kinds", "mode", "limit"];

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const changed = (prev, next, keys) => keys.filter((k) => !same(prev[k], next[k]));

/** Apply `patch` to `prev`: {state, history: "push"|"replace"|"none", refetch}. */
export function planChange(prev, patch) {
  const next = { ...prev, ...patch };
  // Choosing a Focus node from the overview leaves it for the focus view.
  if (patch.focus && !patch.view && prev.view === "overview") next.view = derivedView(next.focus);
  if (!("stubs" in patch) && changed(prev, next, RESET_STUB_KEYS).length) next.stubs = [];
  const diff = changed(prev, next, Object.keys(DEFAULTS).concat("focus"));
  const history = diff.length === 0 ? "none" : changed(prev, next, PUSH_KEYS).length ? "push" : "replace";
  return { state: next, history, refetch: changed(prev, next, REFETCH_KEYS).length > 0 };
}

/** Cap list-valued keys at MAX_EXPANDED. Returns {state, notice}; notice is null when nothing was dropped. */
export function capState(state) {
  const dropped = [];
  const next = { ...state };
  for (const key of ["expanded", "stubs"]) {
    const list = state[key] || [];
    if (list.length > MAX_EXPANDED) { next[key] = list.slice(0, MAX_EXPANDED); dropped.push(`${list.length - MAX_EXPANDED} ${key}`); }
  }
  const notice = dropped.length ? `State truncated: dropped ${dropped.join(" and ")} (limit ${MAX_EXPANDED} each).` : null;
  return { state: next, notice };
}

export const notFoundMessage = (focus) =>
  `Node not found: ${focus}. Was the database re-indexed? Use search to find it again.`;

/**
 * The state holder behind the URL. `location` and `history` are injected (the browser's, or fakes).
 * apply(patch) decides push vs replace via planChange; pushes render through the hashchange the browser
 * fires, replaces render directly (only when the graph must be refetched). render(refetch) and
 * notice(text) are the only outputs.
 */
export function createUrlController({ location, history, render, notice }) {
  const load = () => {
    const { state, notice: n } = capState(parseHash(location.hash));
    if (n) { notice(n); history.replaceState(null, "", formatHash(state) || location.pathname || ""); }
    return state;
  };
  let state = load();
  return {
    get state() { return state; },
    apply(patch) {
      const plan = planChange(state, patch);
      const { state: next, notice: n } = capState(plan.state);
      if (n) notice(n);
      state = next;
      const hash = formatHash(state);
      if (plan.history === "push") location.hash = hash || "#"; // hashchange -> onHashChange -> render
      else if (plan.history === "replace") {
        history.replaceState(null, "", hash || location.pathname || "");
        if (plan.refetch) render(true);
      }
    },
    onHashChange() { state = load(); render(true); },
  };
}

/**
 * Re-expand recorded Stub nodes against a freshly loaded model, in order. `fetchPage(stub)` returns the
 * page or null; `isCurrent()` goes false when a newer render supersedes this one. Returns the ids that
 * were replayed (stale ones, whose stub no longer exists, are dropped).
 */
export async function replayStubs(model, ids, fetchPage, isCurrent) {
  const done = [];
  for (const id of ids) {
    if (!isCurrent()) break;
    const stub = model.view().stubs.find((s) => s.id === id);
    if (!stub) continue;
    const page = await fetchPage(stub);
    if (!isCurrent()) break;
    if (!page) continue;
    model.expand(id, page);
    done.push(id);
  }
  return done;
}
