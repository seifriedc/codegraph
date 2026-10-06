// Recent nodes: last 10 picked from search, kept in browser storage. Storage is injected and
// every access is guarded: private windows / blocked site data must not break the UI.

export const RECENT_MAX = 10;
const KEY = "codegraph.recent";
const FIELDS = ["id", "kind", "name", "qualified_name", "path", "language", "external", "more_paths"];

export function createRecent(storage) {
  let items = load();

  function load() {
    try {
      const v = JSON.parse(storage.getItem(KEY));
      return Array.isArray(v) ? v.slice(0, RECENT_MAX) : [];
    } catch {
      return [];
    }
  }

  return {
    list: () => items.slice(),
    add(node) {
      const slim = Object.fromEntries(FIELDS.map((f) => [f, node[f] ?? null]));
      items = [slim, ...items.filter((n) => n.id !== slim.id)].slice(0, RECENT_MAX);
      try { storage.setItem(KEY, JSON.stringify(items)); } catch { /* keep the in-memory list */ }
    },
  };
}
