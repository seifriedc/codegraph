// Side panel: node details and per-kind neighbor counts. Module has no top-level DOM access.

/** {"in": {calls: 2}, "out": {...}} -> [{kind, in, out}] sorted by kind, zero-filled. */
export function neighborRows(counts) {
  const kinds = new Set([...Object.keys(counts.in || {}), ...Object.keys(counts.out || {})]);
  return [...kinds].sort().map((kind) => ({ kind, in: (counts.in || {})[kind] || 0, out: (counts.out || {})[kind] || 0 }));
}

function el(doc, tag, text, cls) {
  const e = doc.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

/** Render a NodeDetail (or null) into `root`. All text goes through textContent. */
export function renderPanel(root, detail, doc = root.ownerDocument) {
  root.replaceChildren();
  if (!detail) {
    root.append(el(doc, "p", "Select a node by opening #focus=<id or qualified name>.", "muted"));
    return;
  }
  root.append(el(doc, "h2", detail.qualified_name || detail.name));
  const dl = el(doc, "dl");
  const row = (k, v) => { dl.append(el(doc, "dt", k), el(doc, "dd", v)); };
  row("Kind", detail.kind + (detail.external ? " (external)" : ""));
  row("Language", detail.language || "-");
  row("Path", detail.path ? detail.path + (detail.line_start ? `:${detail.line_start}` : "") : "-");
  root.append(dl);

  root.append(el(doc, "h3", `Defined in (${detail.defining_files.length})`));
  const files = el(doc, "ul", null, "files");
  for (const f of detail.defining_files) files.append(el(doc, "li", f));
  if (!detail.defining_files.length) files.append(el(doc, "li", "-", "muted"));
  root.append(files);

  root.append(el(doc, "h3", "Neighbors"));
  const rows = neighborRows(detail.neighbor_counts);
  if (!rows.length) { root.append(el(doc, "p", "none", "muted")); return; }
  const table = el(doc, "table", null, "counts");
  const head = el(doc, "tr");
  for (const h of ["Edge kind", "In", "Out"]) head.append(el(doc, "th", h));
  table.append(head);
  for (const r of rows) {
    const tr = el(doc, "tr");
    tr.append(el(doc, "td", r.kind), el(doc, "td", String(r.in)), el(doc, "td", String(r.out)));
    table.append(tr);
  }
  root.append(table);
}
