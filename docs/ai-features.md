# AI Features: Use Cases, Data Sources, and Plan

This document tracks the design process for adding AI-assisted features on top of
the structural knowledge graph: what questions we want the tool to answer, what
evidence is needed to answer them honestly, and the resulting implementation plan.

## Design principle: separate retrieval, enrichment, and synthesis

Three distinct mechanisms tend to get bundled under "AI features" and are worth
keeping conceptually separate:

- **Retrieval** — finding relevant nodes (semantic/embedding search).
- **Enrichment** — using an LLM to add information to the graph (summaries, role
  tags), written back as node/edge metadata.
- **Synthesis** — using an LLM to reason over retrieved/enriched graph data and
  produce a narrated answer (e.g. `codegraph ask`).

## Use-case catalog

Use cases are grouped by what kind of evidence actually answers the question —
this matters more than surface topic, because it determines which data sources
are required.

### A. Structurally grounded
Answerable exactly from the current graph today (no AI required).

- A1: What calls/imports/inherits from X?
- A2: What's the type hierarchy of X?
- A3: What would statically break if X's signature changed? (transitive callers)

### B. Component/module responsibility & summarization — **priority**
"What is this code, what is it for." Answerable from static structure plus
LLM-generated vocabulary; no dynamic analysis required.

- B1: What code is responsible for track correlation? (responsibility
  identification when the exact name/vocabulary is unknown)
- B2: Find code similar to this function (dedup/refactor candidates)
- B3: Summarize what this file/module does (onboarding)
- B4: Is there dead code? Candidates come from static reachability (nodes with
  no incoming `calls`/`references` edges), but naive unreferenced-ness has many
  false positives (public API surfaces, virtual/interface methods, FFI-exported
  symbols, test fixtures, `main`). LLM judgment on candidates, and eventually
  dynamic coverage data, disambiguate.

### C. Runtime interaction questions
"What actually happens between running components." Static parsing structurally
cannot see these relationships (e.g. no edge links a `send()` in process A to a
`recv()` in process B — they're connected only by a runtime resource name).

- C1: How do these processes communicate via IPC?
- C2: What are the major subsystems and how do they interact at runtime?
- C3 (**backlog**): Is there an architectural violation (e.g. layer X reaching
  into layer Y it shouldn't)? Requires a specification of the intended
  architecture as input, which doesn't exist yet — deferred until that spec is
  available.

### D. Change-impact reasoning
Narrated blast-radius answers and agent context assembly, built mostly on group
A's static traversal.

- D1: If I change X, what breaks, and why does it matter?
- D2: Assemble the right context for an agent to safely modify X.

## Data-source taxonomy

| Source | What it gives you | Reliability | Where it's necessary |
|---|---|---|---|
| **Static analysis** (current graph) | Exact syntactic facts: calls, imports, inherits, contains | Ground truth, but only same-process/compile-time-visible relationships | A1–A3 fully; a necessary substrate for everything else |
| **Semantic embeddings** | Fuzzy concept → code matching | Approximate; quality bounded by what text gets embedded | B1–B2 (retrieval step) |
| **LLM/agent enrichment** | Translates code into domain vocabulary (summaries, role tags); can hypothesize relationships static analysis can't see | Probabilistic — must be flagged as inference, not fact | Makes embedding-based retrieval work for B1–B3; drives C1–C2 hypothesis generation and B4 judgment; narrates D1 |
| **Dynamic analysis** (runtime traces) | Actual observed behavior: which queue/socket/shared-mem segment was touched by which process, at runtime | Only source that can prove a cross-process relationship rather than guess at it | The reliable answer for C1 when channel/queue identifiers aren't static constants; strengthens B4 (coverage data as dead-code evidence) |
| **Other docs** (commit history, comments, design docs, PRs) | More domain vocabulary, often the *reason* something exists | Variable quality, cheap to mine, already git-tracked | Supplements B/C enrichment |

## Cross-cutting requirement: provenance

Every AI-derived answer or graph artifact must carry a provenance tag so
inference is never presented with the same confidence as a parsed fact:

```
provenance: static | embedding | llm_inferred | dynamic
```

`codegraph ask` should be able to say "no static or dynamic link found; LLM
hypothesizes X based on similar queue-naming — unverified" rather than asserting
an LLM-derived relationship as graph fact.

### Schema implications

1. **Edges currently have no `metadata` column** (nodes already do). A future
   dynamic edge (e.g. "process A wrote to queue Q, observed at runtime") doesn't
   naturally have a `file_path`/`line`/`col` — it has a channel identifier, a
   call count, maybe a timestamp range. Add a `metadata` JSON column to `edges`,
   mirroring `nodes`, so new attribute types don't require schema migrations.
2. **Add a `provenance` column** to both `nodes` and `edges` (nullable, defaults
   to `static` for parser-produced rows) using the enum above.
3. **Reuse the existing `graph add-node`/`add-edge` mutation CLI** as the common,
   source-agnostic ingestion path for LLM-enrichment writes and, later, a
   dynamic-trace importer — extended with `--provenance` and `--metadata` flags,
   rather than building separate ingestion code per source.
4. **Open question, not decided yet**: today's node kinds (`file, module,
   package, function, class, method, type, variable`) have nothing representing
   a *process* or *service* — a runtime/deployment concept, not a static one.
   Group C work may eventually want a `process` node kind that dynamic ingestion
   (or a manifest) populates, with `communicates_via` edges hanging off it.
   Deferred until C-group work starts.

## Requirements for group B (priority)

**Functional**
- FR-B1: Given a natural-language description of functionality, return ranked
  candidate nodes likely responsible, each with a similarity score and
  provenance.
- FR-B2: Given a node, return other nodes with similar functionality, ranked by
  similarity.
- FR-B3: Given a file or module node, return a natural-language summary of its
  purpose/responsibilities.
- FR-B4: Return ranked dead-code candidates (nodes with no static incoming
  references), each annotated with an LLM judgment of likely-intentional vs.
  likely-dead and a provenance tag. Never auto-delete — surface for human
  review only.

**Non-functional**
- NFR-1 (Provenance): every AI-derived answer/artifact carries a provenance tag
  (see above).
- NFR-2 (Incrementality/cost): enrichment and embedding generation are
  incremental, gated by content hash, so re-runs only touch changed nodes.
- NFR-3 (Offline/deterministic tests): LLM calls are mockable so the existing
  integration-test convention (fixtures in `tests/`) stays deterministic and
  offline.
- NFR-4 (Configurability): LLM provider/model is configurable — sending source
  to an external API is a decision the user controls, not a hardcoded default.
- NFR-5 (Additive schema): schema changes are additive/nullable so existing
  databases and queries keep working without a forced re-index.

## Phased plan (group B)

**Phase 0 — Foundation & schema**
- Add `metadata` and `provenance` columns to `edges` (mirrors `nodes`); default
  `provenance = static` for parser-produced rows. Unblocks group C later without
  another migration.
- `codegraph/llm.py`: configurable LLM client wrapper (provider/model via
  config/env).
- `embeddings` table: `(node_id, vector, source, provenance, created_at)`;
  brute-force cosine via DuckDB array functions is sufficient at single-repo
  node counts — no ANN index needed yet.
- Minimal internal context-bundle helper (code snippet + immediate static
  context) in `query.py`, used as LLM input in Phase 1. Not exposed as a public
  CLI command yet (that's group D, not prioritized) — but built once here so
  D doesn't require rework later.

**Phase 1 — Enrichment (drives B1, B3; feeds B4)**
- `codegraph enrich` CLI: for function/class/method/module nodes, generate an
  LLM summary + role tags, written to `node.metadata.ai` (`summary`, `tags`,
  `provenance: llm_inferred`, `generated_at`, `model`, `content_hash`).
  Content-hash gated for incremental runs.
- File/module-level summaries (B3) aggregate child-node summaries bottom-up
  rather than re-reading the whole file, keeping cost down and summaries
  consistent with function-level enrichment.

**Phase 2 — Semantic search (drives B1 retrieval, B2)**
- Embed enrichment summaries (fallback to raw code+comments for un-enriched
  nodes) into the `embeddings` table.
- `codegraph query similar <node-id-or-free-text> --top-k N`: nearest-neighbor
  lookup, results scored and provenance-tagged (`embedding`, referencing the
  underlying `llm_inferred` summary that matched).
- B1 becomes: free-text query → embedding search → ranked candidates, each
  showing its matched summary and provenance chain.

**Phase 3 — Dead code detection (B4)**
- Static pass: nodes with zero incoming `calls`/`references` edges (excluding
  conventional entry points) → candidates, `provenance = static`.
- LLM classification pass reuses Phase 1 role tags to flag likely-intentional
  candidates (public API, test fixture, entry point) vs. likely-dead,
  `provenance = llm_inferred`. Always a candidate list for human review, never
  an automatic deletion.
- Future (not in this phase): dynamic coverage data upgrades confidence further
  — the provenance/dynamic hook from Phase 0 makes this a pure addition, not a
  rework.

## Deferred / backlog

- **C1/C2 (runtime interaction questions)**: requires the schema extensions
  above plus, eventually, dynamic trace ingestion to move from LLM hypothesis to
  verified fact. Design supports this; not being built now.
- **C3 (architectural conformance)**: requires an intended-architecture spec as
  input; revisit once that spec exists.
- **D (change-impact reasoning / agent context assembly)**: builds on group A
  plus the Phase-0 context-bundle helper; not the current priority but shares
  plumbing with B, so later work here should be cheap.
