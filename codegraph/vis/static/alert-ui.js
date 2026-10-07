// The Alert button: a triangle "!" in the Toolbar, coloured by the worst active severity, with a count badge.
// Clicking opens a popover listing the messages, each with an action (optional) and a dismiss "x", and "Clear all".
// Renders into `root` from an alerts model (alerts.js); all text goes through textContent.

const SVG_NS = "http://www.w3.org/2000/svg";

function el(doc, tag, text, cls) {
  const e = doc.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

function triangleIcon(doc) {
  const s = doc.createElementNS(SVG_NS, "svg");
  for (const [k, v] of Object.entries({ width: 14, height: 14, viewBox: "0 0 16 16", "aria-hidden": "true" })) s.setAttribute(k, String(v));
  const part = (tag, attrs) => {
    const p = doc.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) p.setAttribute(k, String(v));
    s.append(p);
  };
  part("path", { d: "M8 1.5 15 14H1z", fill: "none", stroke: "currentColor", "stroke-width": 1.5, "stroke-linejoin": "round" });
  part("path", { d: "M8 6v4", stroke: "currentColor", "stroke-width": 1.6, "stroke-linecap": "round" });
  part("circle", { cx: 8, cy: 12, r: 0.9, fill: "currentColor" });
  return s;
}

function messageRow(doc, m, alerts) {
  const row = el(doc, "div", null, `alert-msg ${m.severity}`);
  row.append(el(doc, "span", m.text, "alert-text"));
  if (m.action) {
    const act = el(doc, "button", m.action.label);
    act.type = "button";
    act.addEventListener("click", () => { m.action.run(); alerts.dismiss(m.key); });
    row.append(act);
  }
  const x = el(doc, "button", "×", "alert-x");
  x.type = "button"; x.title = "Dismiss"; x.setAttribute("aria-label", "Dismiss");
  x.addEventListener("click", () => alerts.dismiss(m.key));
  row.append(x);
  return row;
}

export function mountAlertButton(root, alerts, doc = root.ownerDocument) {
  let open = false;

  function render() {
    const msgs = alerts.list();
    if (!msgs.length) open = false; // nothing left to show: close
    root.replaceChildren();
    const btn = el(doc, "button", null, "alert-btn");
    btn.type = "button";
    btn.dataset.severity = alerts.worst();
    btn.title = msgs.length ? `${msgs.length} alert${msgs.length === 1 ? "" : "s"}` : "No alerts";
    btn.setAttribute("aria-expanded", String(open));
    btn.append(triangleIcon(doc));
    if (msgs.length) btn.append(el(doc, "span", String(msgs.length), "alert-badge"));
    btn.addEventListener("click", () => { open = !open; render(); });
    root.append(btn);
    if (!open) return;
    const pop = el(doc, "div", null, "alert-pop");
    pop.setAttribute("role", "status");
    for (const m of msgs) pop.append(messageRow(doc, m, alerts));
    const clear = el(doc, "button", "Clear all");
    clear.type = "button";
    clear.addEventListener("click", () => alerts.dismissAll());
    pop.append(el(doc, "div", null, "alert-foot"));
    pop.lastChild.append(clear);
    root.append(pop);
  }

  alerts.subscribe(render);
  // composedPath is captured at dispatch, so it still includes the button after render() replaced it.
  doc.addEventListener("click", (e) => {
    if (open && !e.composedPath().includes(root)) { open = false; render(); }
  });
  render();
  return { render };
}
