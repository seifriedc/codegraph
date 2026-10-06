# Materialize package nodes at index time; derive aggregate edges at query time

The overview needs Groups. Packages (and their `contains` hierarchy) are materialized by the parsers as real nodes and edges so agents and the viz both query them. Aggregate edges between Groups are derived in the query layer, because they depend on the active edge-kind filter and collapse state and would otherwise go stale or explode combinatorially.

## Consequences

- Parser change: Ada emits parent-package → child-package `contains` edges. C and C++ use `file` nodes as Groups; no new unit node.
- C++ namespaces are deferred to a separate feature (they would become Packages).
## Considered Options

- **Rejected: infer Groups and nesting at query time only** (e.g. split Ada qualified names on `.` to find `Geometry` as parent of `Geometry.Utils`). Simpler, no schema or parser change. Rejected because the hierarchy would be visible only to the viz, not queryable by agents via the CLI or `Graph`, and it would diverge from the graph model where `contains` already expresses membership.
- **Rejected: also materialize Aggregate edges** (one stored edge per Group pair, per kind, with counts). Makes reads trivial. Rejected because counts depend on the active edge-kind filter and on collapse state (expanding a Group replaces its Aggregate edges with member-level ones), so stored aggregates would go stale on re-index or need a variant per filter/collapse combination.
