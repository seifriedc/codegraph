// View state <-> URL hash. Pure (no DOM): the URL is the source of truth for view state.
// Other views add their own keys here (mode, kinds, group-by, ...); unknown keys are ignored.
//
// `view` picks the screen. Default: "focus" when a focus node is given, else "overview" (the landing view).
// Overview-only keys: `expanded` (repeated `expanded=<group id>`), `okinds` (edge kinds; absent = server
// default, which leaves `calls` off), `groupby` ("directory"; ticket 25 adds "package").

export const DEFAULTS = Object.freeze({
  depth: 2, direction: "both", view: "overview", expanded: Object.freeze([]), okinds: null, groupBy: "directory",
});
export const MAX_UI_DEPTH = 5;
export const DIRECTIONS = ["both", "in", "out"];
export const VIEWS = ["overview", "focus"]; // other views append here
export const GROUP_BYS = ["directory"]; // ticket 25 appends "package"

const derivedView = (focus) => (focus ? "focus" : "overview");

/** "#focus=Shape&depth=3" -> full state. Invalid values fall back to defaults. */
export function parseHash(hash) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const depth = Number.parseInt(p.get("depth"), 10);
  const direction = p.get("direction");
  const focus = p.get("focus") || null;
  const view = p.get("view");
  const groupBy = p.get("groupby");
  return {
    focus,
    view: VIEWS.includes(view) ? view : derivedView(focus),
    depth: depth >= 1 && depth <= MAX_UI_DEPTH ? depth : DEFAULTS.depth,
    direction: DIRECTIONS.includes(direction) ? direction : DEFAULTS.direction,
    expanded: p.getAll("expanded"),
    okinds: p.has("okinds") ? p.get("okinds").split(",").filter(Boolean) : null,
    groupBy: GROUP_BYS.includes(groupBy) ? groupBy : DEFAULTS.groupBy,
  };
}

/** Inverse of parseHash; values equal to the defaults are omitted to keep URLs short. */
export function formatHash(state) {
  const p = new URLSearchParams();
  if (state.view && state.view !== derivedView(state.focus)) p.set("view", state.view);
  if (state.focus) p.set("focus", state.focus);
  if (state.depth !== DEFAULTS.depth) p.set("depth", String(state.depth));
  if (state.direction !== DEFAULTS.direction) p.set("direction", state.direction);
  for (const id of state.expanded || []) p.append("expanded", id);
  if (state.okinds) p.set("okinds", state.okinds.join(","));
  if (state.groupBy && state.groupBy !== DEFAULTS.groupBy) p.set("groupby", state.groupBy);
  const s = p.toString();
  return s ? "#" + s : "";
}
