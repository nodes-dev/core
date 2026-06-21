# nodes — Shared Knowledge Substrate (Design)

- **Status:** Draft (design approved, pending spec review)
- **Date:** 2026-06-21
- **Working name:** `nodes` (revisit before publishing a package — see [Naming](#12-naming))
- **Scope:** Phase 1 — design the shared data model / substrate. Mindful v6 and any
  `science` refactor are *downstream* specs that build on this.

## 1. Motivation & goals

Two existing systems — `~/d/mindful/` (a graph-based markdown tool-for-thought, human
audience) and `~/d/science/` (a research-project + knowledge-graph system, human + AI-agent
audience) — independently converged on the same shape: **entities containing markdown +
metadata, linked by relations, composed into graph structures.** They share topics and
concepts but have no common data model.

`nodes` is a **problem-agnostic core**: the data model + machinery for creating and operating
on graph-structured representations of knowledge and ideas. Both applications build on it:

- **science** = a research-oriented application built on `nodes`
- **mindful** = a personal knowledgebase / tool-for-thought built on `nodes`

### Goals

- One shared, language-agnostic data model + on-disk format for both projects.
- A clean seam between **plumbing** (structural machinery) and **domain** (application kinds).
- Features added at the plumbing level are available to all downstream applications.
- A simple, intuitive mental model: *nodes + relations*, with everything else composed on top.
- Support fast thought/entity I/O (search + CRUD) — the first concrete consumer is Mindful v6.

### Non-goals (deferred — YAGNI)

- **Multi-user / multi-author authorship** ("ownership of prose"). The long-term goal, but
  neither system exercises it yet; designing it now adds schema + resolution complexity for
  no current need. Today: single author per context (mindful = one human, science = one
  agent). Entities have a plain markdown body. We leave a clean seam to add authorship later.
- **Cross-project federation** (peer references across repos).
- **Advanced network operations** (sampling, graph algorithms) — later library phases.

## 2. Architecture: three layers

Same repo, distinct modules, with a strict dependency direction: **domain profiles depend on
the vocab + kernel; the vocab depends on the kernel; the kernel depends on no layer below it**
(and on no domain). Nothing below the kernel may leak upward into it.

```
kernel           Node, Relation, structural shapes, identity grammar, on-disk format,
                 CRUD, validation, registry, derived index.
                 Domain-free plumbing. ZERO named knowledge kinds.

knowledge vocab  A standard, separately-importable profile of generally-useful
                 knowledge-representation kinds: note/idea, question, topic, paper,
                 book, dataset, ...

domain layers    science  (hypothesis, evidence-line, proposition, patch, ...)
                 mindful  (thought, mindmap, journal, attractor, ...)
                 bio-nodes (gene, protein, pathway, ...)
```

Rationale: keeping the kernel ruthlessly domain-free makes the plumbing/domain separation
explicit (not merely conventional), and lets the machinery be reused for non-knowledge
graphs. The knowledge vocabulary ships *with* `nodes` but lives one layer above the kernel.

## 3. Kernel data model

### 3.1 Node

The universal container. Every node has:

| Field | Notes |
|-------|-------|
| `id` | Canonical, human-friendly: `kind:slug` (e.g. `topic:polycomb`, `thought:mindful-ideas`). |
| `uid` | Immutable UUID. Carried on **every** node (consistency/simplicity) so references survive renames. |
| `kind` | The node's type name; resolved against the registry. |
| `title` | Human-readable display title. |
| `body` | Markdown content (single author per context, for now). |
| `metadata` | `created`, `updated`, `version`, … (structural/system metadata). |
| `related` | Sugar list of untyped backlinks (`predicate: relatesTo`). |
| `relations` | Typed relations (see 3.2). |
| `facets` | Registry-validated map of typed payloads (see 3.3). |

A node's *alias* (mindful's term) **is** its slug. The full identity / reference / rename
contract — stored form, display form, rename behavior, collisions — is specified in §3.5.

### 3.2 Relation — the single edge primitive

There is one edge concept, not three. `Edge`, `related:`, and `tag` all reduce to it.

```
Relation = { source, predicate, target, directed?, weight?, attrs? }
```

- `related: [ref, ...]` is **sugar** for relations with `predicate: relatesTo`.
- A **tag** (mindful) is the same: `#alias` → a `relatesTo` relation, resolved by alias → id.
- An **edge** is just a Relation that lives *inside* a graph structure (3.4).
- `relations:` carries typed semantic links (`predicate` = `cites`, `supports`, `refines`, …),
  generalizing science's existing `related:` + `relations:` split.

**Normalized vs serialized forms.** The shape above is the *normalized* (in-memory / indexed)
form, where `source` is always explicit. On disk, `source` is **implied by location**, giving
two serialized shapes:

- **Node-relation** (in a node's `related:` / `relations:`): `{ predicate, target, … }` —
  `source` is the containing node's `id`, omitted from the file.
- **Graph edge** (in a structure's `edges:`): `{ source, target, predicate, … }` — both
  endpoints are members of the structure, so both are explicit; the structure node is the
  container, not an endpoint.

Parser contract: deserialize by filling `source` from context into the normalized form;
serialize by dropping `source` only when it equals the container node. The Python and TS
parsers MUST round-trip these two shapes identically.

### 3.3 Facets & the registry — specialization model

Decision: **facet composition for domain types; constraint refinement for structural shapes.**

- A **facet** is a typed payload attached to a node (e.g. `Tabular`, `Provenance`, `BioAxes`,
  `VisualIdentity`, `Membership`).
- A **kind** is defined by *a name + a set of required/optional facets + invariants*, enforced
  by a **registry**. It is **not** a deep subclass chain.
- **Domain specialization = adding facets** (independent axes compose instead of linearizing):

  ```
  gene-expression-matrix = Node + { Tabular, Provenance, BioAxes }
  thought                = note + { VisualIdentity }
  ```

This replaces inheritance chains like `Node ← Dataset ← Matrix ← BioMatrix ←
GeneExpressionMatrix`, which collapse several independent axes (tabular-ness, provenance,
biological semantics) into one rigid is-a spine.

The **one narrow, honest use of refinement** is the structural shapes (3.4), where each level
genuinely narrows the one above by adding invariants.

### 3.4 Structural shapes — the refinement lattice

```
Set ─┬─ List   (+ order, duplicates allowed)
     └─ Dict   (+ unique keys)
Graph → DAG → Tree   (+ acyclicity, + single-parent)
```

`List` and `Dict` are **siblings** that refine `Set` along different axes — `List` adds
ordering, `Dict` adds keying — rather than a single `Set → List → Dict` chain (a dict is not a
narrowed list). A structure is a Node carrying a **Membership facet** whose shape and
multiplicity rules depend on the kind:

| Shape | Membership facet | Multiplicity / order |
|-------|------------------|----------------------|
| Set   | `members: [ref]` | unique, unordered |
| List  | `members: [ref]` | ordered, duplicates allowed |
| Dict  | `members: { key: ref }` | unique keys; insertion order preserved, not semantic |
| Graph | `members: [ref]` + `edges: [Relation]` | unique members |
| DAG   | Graph + acyclicity invariant | — |
| Tree  | DAG + single-parent invariant | — |

Membership edges are **first-class Relations** (the index sees them) but are stored *on the
structure node* for locality and ordering. This generalizes mindful v5's proven
`members` / `order` / `edges` shape (members carried prefixes like `th:` / `ts:`).

Downstream specializations compose on top:

```
NodeGraph → ThoughtGraph (mindmap)
NodeGraph → NodeDAG → CausalDAG
NodeList  → ThoughtList (journal)
```

### 3.5 Identity, references & rename — contract

- **Stored ref form:** the human-friendly canonical **`id`** (`kind:slug`) everywhere in files —
  in `relations:`, in membership `members` / `edges`, and in prose / tag links. Git-diffable
  and readable.
- **Display ref form:** the same `id` (or the target's `title` in rendered UI). Tags display as
  `#slug`.
- **`uid` role:** every `id` resolves (via the index) to the target node's immutable **`uid`**,
  which is the join key and the identity that survives a rename. `uid` is the *anchor*, not the
  stored ref form.
- **Rename behavior:** changing a node's slug/`id` is a **library operation** that (1) updates
  the node's `id`, (2) appends the previous `id` to its `deprecated_ids`, and (3) rewrites
  inbound refs across the corpus (mechanical and safe because files are local + git-versioned).
  The node's `uid` never changes, so the index keeps its identity throughout; any un-rewritten
  or stale ref still resolves through `deprecated_ids → uid`. This is how `uid` *protects links*
  without forcing `uid` into prose/tags.
- **Collision rules:** `id` is unique across the corpus — the registry/index rejects a second
  node claiming a live `id`, or one claiming another node's still-active `deprecated_id` (fail
  early). `uid` is globally unique by construction.

## 4. On-disk format

- **Canonical store:** markdown + YAML frontmatter, **one file per node**, **git-versioned**.
  Files are the single source of truth; everything else is rebuildable from them.
- Kernel-universal fields stay **top-level** in frontmatter: `id`, `uid`, `kind`, `title`,
  `created`, `updated`, `related`, `relations`.
- Facet payloads live under a **nested `facets:` map**, keyed by facet name (chosen over flat
  namespaced keys for composition clarity).
- The markdown **body** is everything below the frontmatter.

```yaml
---
id: gene:PHF19
uid: 7b2c…-…-…
kind: gene
title: PHF19
created: 2026-06-21
updated: 2026-06-21
related: [pathway:PRC2, topic:polycomb]
relations:
  - { predicate: interacts_with, target: gene:EZH2 }
facets:
  bio-axes: { primary_external_id: HGNC:7296 }
---
PHF19 is a PRC2-associated component …
```

The `relations:` entry above omits `source` — per §3.2 it is implied to be `gene:PHF19`, the
containing node.

## 5. Derived index & fast I/O

A **rebuildable index** (never hand-edited, fully reconstructable from the files) backs fast
CRUD/search:

- full-text search (ripgrep-class),
- the resolved relation graph,
- alias/slug → id/uid resolution,
- an embedding + similarity store.

Files stay canonical; the index is disposable cache. This is what lets Mindful v6 hit
"performant thought I/O" without a database-of-record, and keeps the human/AI git workflow
intact.

## 6. Libraries

- A **language-agnostic spec** defines the building blocks: `Node`, `Relation`, the structural
  shapes (`NodeSet`, `NodeList`, `NodeDict`, `NodeGraph`, `NodeDAG`, `NodeTree`), the identity
  grammar, the on-disk format, and the registry/validation rules.
- **Python** and **TypeScript** implementations share one API surface: CRUD, parse/serialize,
  relation/graph queries, validation, index build/query.
- **Later phases:** general, widely-useful operations such as sampling and network operations.

## 7. Mapping the two applications onto `nodes` (validation)

### science

The kernel is **extracted from** the existing `science_model` package, which already provides
`Entity`, a registry, frontmatter parsing, the `kind:slug` id grammar, and `related:` /
`relations:`. Migration is incremental and low-risk:

- relabel `Entity → Node` (`science_model` becomes a thin domain profile on the kernel),
- move research kinds (`hypothesis`, `evidence-line`, `proposition`, `patch`, …) into a
  `science` profile,
- map science's typed entity subclasses onto facets where they represent independent axes.

### mindful (v6)

Greenfield on the kernel:

- `thought` = `note` + `VisualIdentity` facet,
- mindmap = `NodeGraph` (→ `ThoughtGraph`); journal = `NodeList` (→ `ThoughtList`),
- **tags** = `related` entries resolved by alias,
- attractors / visual identity / scene data = facets + derived index,
- former CouchDB store → markdown + git + derived index.

## 8. Resolved decisions

1. **Canonical store:** markdown + git; fast I/O via a rebuildable derived index on top.
2. **Authorship / multi-user:** deferred. Single author per context; plain markdown body.
3. **Sharing mechanism:** a neutral core both apps build on (not science-as-base).
4. **Boundary:** domain-free kernel + separable knowledge-vocab layer + domain layers.
5. **Specialization:** facet composition for domains; constraint refinement for shapes.
6. **Relations:** one `Relation` primitive; `related:`, tags, and graph edges are all sugar/uses of it.
7. **Structures:** membership facet stored on the structure node; edges are first-class Relations.
8. **Identity:** `kind:slug` canonical id (the stored + display ref form) + immutable `uid`
   (UUID) on every node as the identity anchor; rename rewrites inbound refs and records
   `deprecated_ids` (§3.5).
9. **Facet serialization:** nested `facets:` map in frontmatter.
10. **Home:** new `~/d/nodes/` repo; `~/d/mindful/v6/` reserved for the future mindful app.

## 9. Open / deferred

- **Deferred (YAGNI):** multi-user/authorship, cross-project federation, advanced network ops.
- **To settle during implementation planning:** exact registry/profile manifest format;
  index technology choice; precise Python/TS API surface; the `attrs` vocabulary on relations.

## 10. Migration path (incremental, not a rewrite)

1. Extract the kernel from `science_model`; ship the knowledge-vocab layer.
2. Land Python + TS kernel libraries + spec + derived index.
3. Refactor `science` to sit on the kernel via a `science` profile (relabel, move kinds).
   **`uid` backfill:** `science_model.Entity` carries `id` / `canonical_id` but no `uid`; a
   one-time migration mints `uid = uuidv5(NODES_NAMESPACE, canonical_id)` for every existing
   entity and writes it into frontmatter, after which it is immutable regardless of later `id`
   changes. A bounded migration window lets the parser mint-and-write-back a missing `uid`; in
   steady state a missing `uid` is a validation error (fail early). Test fixtures gain expected
   `uid` values from the same deterministic rule.
4. Build Mindful v6 core (search + CRUD CLI) greenfield on the kernel.

Each step is a separate downstream spec/plan.

## 11. Why this shape

- **Composition over inheritance:** facets keep independent axes independent; the only
  hierarchy is the structural-shape lattice, where refinement is truthful.
- **Explicit over defensive / fail early:** the registry validates kinds against required
  facets and invariants at parse time.
- **Plumbing/domain separation** is structural, not conventional — enforced by the layering.

## 12. Naming

`nodes` conveys the graph intent and is serviceable as a working name. Costs: it is generic
and awkward to grep/package (npm + PyPI namespacing, searchability); the Node.js clash is
minor. Distinctive alternatives floated: `substrate`, `lattice`, `tessera` (mosaic tile — a
composition metaphor), `weft` (the threads a fabric is woven on). Low-stakes and reversible;
decide before publishing a package.
