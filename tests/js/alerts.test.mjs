// The Alert button's model: severity, dismissal and recurrence. node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { createAlerts } = await import(path.join(here, "..", "..", "codegraph", "vis", "static", "alerts.js"));

test("worst severity is none, alert or error; errors list first", () => {
  const a = createAlerts();
  assert.equal(a.worst(), "none");
  a.set("crowded", "alert", "crowded");
  assert.equal(a.worst(), "alert");
  a.set("error", "error", "boom");
  assert.equal(a.worst(), "error");
  assert.deepEqual(a.list().map((m) => m.key), ["error", "crowded"]);
});

test("setting the same key again updates it rather than adding a second message", () => {
  const a = createAlerts();
  a.set("crowded", "alert", "300 nodes");
  a.set("crowded", "alert", "400 nodes");
  assert.deepEqual(a.list().map((m) => m.text), ["400 nodes"]);
});

test("a dismissed condition stays hidden while it persists, and returns after it resolves and recurs", () => {
  const a = createAlerts();
  a.set("crowded", "alert", "crowded");
  a.dismiss("crowded");
  assert.equal(a.worst(), "none");
  a.set("crowded", "alert", "still crowded"); // re-raised on every re-render
  assert.equal(a.list().length, 0);
  a.resolve("crowded");
  a.set("crowded", "alert", "crowded again");
  assert.deepEqual(a.list().map((m) => m.text), ["crowded again"]);
});

test("dismissAll hides everything currently shown", () => {
  const a = createAlerts();
  a.set("x", "alert", "x");
  a.set("y", "error", "y");
  a.dismissAll();
  assert.equal(a.worst(), "none");
});

test("subscribers hear about changes and can unsubscribe", () => {
  const a = createAlerts();
  let n = 0;
  const off = a.subscribe(() => n++);
  a.set("x", "alert", "x");
  a.dismiss("x");
  a.resolve("x");
  assert.equal(n, 3);
  off();
  a.set("x", "alert", "x");
  assert.equal(n, 3);
});
