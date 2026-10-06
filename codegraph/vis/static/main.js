// Placeholder UI entry point (plain ES module, no build step).
const res = await fetch("/api/stats");
const stats = await res.json();
document.getElementById("status").textContent =
  `${stats.total_nodes} nodes, ${stats.total_edges} edges`;
