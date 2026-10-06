// Top-bar search box: DOM glue around the pure model in search.js and recent.js.
import { createSearchModel, isFocusShortcut, resultRow } from "./search.js";

// Chip options. TODO(visual-encoding ticket): replace with the legend's shared filter model.
// Interface assumed: filters = {kinds: string[], languages: string[]}, pushed in via model.setFilters().
export const KIND_CHIPS = ["class", "type", "function", "method", "package", "module", "file", "variable", "field"];
export const LANGUAGE_CHIPS = ["ada", "c", "cpp"];

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

/**
 * Mounts into `root` (an empty element). Callbacks: onFocus(node) for Enter, onAdd(node) for Shift-Enter.
 * Returns {focusInput()} so other views (e.g. the Overview) can focus the box.
 */
export function mountSearch(root, { fetchFn, recent, onFocus, onAdd }) {
  const input = el("input", "s-input");
  input.type = "search";
  input.placeholder = "Search nodes ( / or Ctrl-K )";
  input.setAttribute("aria-label", "Search nodes");
  input.autocomplete = "off";
  const chips = el("div", "s-chips");
  const drop = el("div", "s-drop");
  drop.hidden = true;
  root.append(input, chips, drop);

  const filters = { kinds: new Set(), languages: new Set() };
  const model = createSearchModel({ fetchFn, onChange: render });

  for (const [group, values] of [["kinds", KIND_CHIPS], ["languages", LANGUAGE_CHIPS]]) {
    for (const v of values) {
      const b = el("button", "s-chip", v);
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("mousedown", (e) => e.preventDefault()); // keep input focus
      b.addEventListener("click", () => {
        filters[group].has(v) ? filters[group].delete(v) : filters[group].add(v);
        b.setAttribute("aria-pressed", String(filters[group].has(v)));
        model.setFilters({ kinds: [...filters.kinds], languages: [...filters.languages] });
      });
      chips.append(b);
    }
  }

  function rowEl(n, selected, onPick) {
    const r = resultRow(n);
    const li = el("div", "s-row" + (selected ? " selected" : ""));
    li.setAttribute("role", "option");
    const top = el("div", "s-top");
    top.append(el("span", "s-kind", r.kind), el("span", "s-name", r.shortName), el("span", "s-lang", r.language || "?"));
    li.append(top);
    if (r.qualifiedName !== r.shortName) li.append(el("div", "s-qn", r.qualifiedName));
    li.append(el("div", "s-path", r.pathText));
    li.addEventListener("mousedown", (e) => { e.preventDefault(); onPick(n, e.shiftKey); });
    return li;
  }

  function render(s) {
    drop.replaceChildren();
    const show = document.activeElement === input;
    if (!show) { drop.hidden = true; return; }
    if (s.query.trim().length === 0) {
      const items = recent.list();
      if (items.length) drop.append(el("div", "s-head", "Recent"));
      items.forEach((n) => drop.append(rowEl(n, false, pick)));
      drop.hidden = items.length === 0;
      return;
    }
    if (s.error) drop.append(el("div", "s-note", `Search failed: ${s.error}`));
    else if (s.query.trim().length < 2) drop.append(el("div", "s-note", "Type at least 2 characters"));
    else if (!s.loading && s.results.length === 0) drop.append(el("div", "s-note", "No matches"));
    s.results.forEach((n, i) => drop.append(rowEl(n, i === s.selected, pick)));
    if (s.note) drop.append(el("div", "s-note", s.note));
    drop.hidden = false;
    drop.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
  }

  function pick(node, add) {
    recent.add(node);
    (add ? onAdd : onFocus)(node);
    input.blur();
  }

  input.addEventListener("input", () => model.setQuery(input.value));
  input.addEventListener("focus", () => render(model.state()));
  input.addEventListener("blur", () => { drop.hidden = true; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && model.state().query.trim().length === 0) return;
    const action = model.key(e);
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter") e.preventDefault();
    if (!action) return;
    if (action.type === "close") { input.value = ""; input.blur(); }
    else pick(action.node, action.type === "add");
  });

  const focusInput = () => { input.focus(); input.select(); };
  addEventListener("keydown", (e) => {
    if (isFocusShortcut(e, document.activeElement?.tagName)) { e.preventDefault(); focusInput(); }
  });

  return { focusInput };
}
