// Search box logic. Pure (no DOM): timers and the fetch function are injected so it is testable under node.

export const MIN_CHARS = 2;
export const DEBOUNCE_MS = 150;

const EMPTY_FILTERS = Object.freeze({ kinds: [], languages: [] });

/**
 * Type-ahead model. `filters` is {kinds: [], languages: []}; it is a local stand-in for the
 * shared legend filter model (supply updates via setFilters()).
 * Keyboard: key(e) returns an action {type: "focus"|"add"|"close", node?} or null.
 */
export function createSearchModel({ fetchFn, setTimer = setTimeout, clearTimer = clearTimeout, onChange = () => {} }) {
  let s = blank("", EMPTY_FILTERS);
  let timer = null;
  let seq = 0; // responses for superseded queries are dropped

  function blank(query, filters) {
    return { query, filters, results: [], total: 0, truncated: false, note: "", selected: 0, loading: false, error: null };
  }
  const set = (patch) => { s = { ...s, ...patch }; onChange(s); };
  const active = () => s.query.trim().length >= MIN_CHARS;

  function schedule() {
    if (timer != null) clearTimer(timer);
    timer = null;
    seq++;
    if (!active()) {
      set({ results: [], total: 0, truncated: false, note: "", selected: 0, loading: false, error: null });
      return;
    }
    set({ loading: true });
    timer = setTimer(run, DEBOUNCE_MS);
  }

  async function run() {
    timer = null;
    const mine = ++seq;
    const query = s.query.trim();
    try {
      const r = await fetchFn(query, s.filters);
      if (mine !== seq) return;
      const n = r.nodes.length;
      set({
        results: r.nodes, total: r.total, truncated: r.truncated, selected: 0, loading: false, error: null,
        note: r.truncated ? `Showing ${n} of ${r.total} matches` : "",
      });
    } catch (err) {
      if (mine === seq) set({ loading: false, error: err.message, results: [] });
    }
  }

  return {
    state: () => s,
    setQuery(q) { s = { ...s, query: q }; schedule(); },
    setFilters(filters) { s = { ...s, filters: { ...EMPTY_FILTERS, ...filters } }; schedule(); },
    key(e) {
      switch (e.key) {
        case "ArrowDown":
          set({ selected: Math.min(s.selected + 1, Math.max(s.results.length - 1, 0)) });
          return null;
        case "ArrowUp":
          set({ selected: Math.max(s.selected - 1, 0) });
          return null;
        case "Enter": {
          const node = s.results[s.selected];
          return node ? { type: e.shiftKey ? "add" : "focus", node } : null;
        }
        case "Escape":
          s = blank("", s.filters);
          schedule();
          return { type: "close" };
        default:
          return null;
      }
    },
  };
}

/** "/" or Ctrl/Cmd-K focuses the search box; "/" is ignored while typing in a field. */
export function isFocusShortcut(e, activeTag) {
  const typing = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT";
  if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) return !typing;
  return Boolean((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K"));
}

/** Display fields for one result row (also used by the recent-nodes list). */
export function resultRow(n) {
  const more = n.more_paths > 0 ? ` +${n.more_paths} more` : "";
  return {
    id: n.id,
    shortName: n.name,
    qualifiedName: n.qualified_name || n.name,
    kind: n.kind,
    language: n.language,
    pathText: n.path ? n.path + more : "external",
  };
}

/** Union of two graph responses by id (Shift-Enter "add to canvas"); the current focus stays. */
export function mergeGraphs(current, added) {
  if (!current) return added;
  const union = (a, b) => {
    const seen = new Set(a.map((x) => x.id));
    return [...a, ...b.filter((x) => !seen.has(x.id))];
  };
  return {
    focus: current.focus,
    nodes: union(current.nodes, added.nodes),
    edges: union(current.edges, added.edges),
    truncated: current.truncated || added.truncated,
    total: Math.max(current.total, added.total),
  };
}
