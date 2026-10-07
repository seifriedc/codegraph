// Alerts: the model behind the toolbar's Alert button. Pure (no DOM): one entry per condition `key`.
// A dismissed condition stays hidden while it persists and comes back only after it has resolved and recurred.

const RANK = { error: 2, alert: 1 };

export function createAlerts() {
  const entries = new Map(); // key -> {key, severity, text, action, dismissed}
  const listeners = new Set();
  const changed = () => listeners.forEach((fn) => fn());

  return {
    /** Raise (or update) a condition. `action` is {label, run}. Re-raising a dismissed condition leaves it dismissed. */
    set(key, severity, text, action = null) {
      const prev = entries.get(key);
      entries.set(key, { key, severity, text, action, dismissed: prev ? prev.dismissed : false });
      changed();
    },
    /** The condition no longer holds: forget it, including any dismissal. */
    resolve(key) {
      if (entries.delete(key)) changed();
    },
    dismiss(key) {
      const e = entries.get(key);
      if (e && !e.dismissed) { e.dismissed = true; changed(); }
    },
    dismissAll() {
      for (const e of entries.values()) e.dismissed = true;
      changed();
    },
    /** Visible messages, errors first (stable within a severity). */
    list() {
      return [...entries.values()].filter((e) => !e.dismissed).sort((a, b) => RANK[b.severity] - RANK[a.severity]);
    },
    /** "none" | "alert" | "error": the worst visible severity. */
    worst() {
      const [top] = this.list();
      return top ? top.severity : "none";
    },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
}
