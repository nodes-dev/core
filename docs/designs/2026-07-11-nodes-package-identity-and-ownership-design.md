# Nodes package identity and ownership

- **Date:** 2026-07-11
- **Status:** Accepted
- **Scope:** Public package names, repository ownership, package-family boundaries,
  and release coordination

## 1. Context

The repository contains Python and TypeScript implementations of one portable
knowledge-representation substrate. The public product is broader than the internal
kernel layer: it includes the on-disk format, identity and mutation semantics,
structural shapes, derived indexes, and a small general-purpose knowledge vocabulary.

The working names (`nodes` on PyPI and `@nodes/kernel` on npm) are unsuitable public
identities. The unscoped `nodes` name is already claimed on both registries, and
`@nodes/kernel` depends on control of an unrelated `nodes` npm scope. Calling the whole
distribution a "kernel" would also understate its intended base vocabulary.

The package family must support reusable domain vocabularies. Applications such as
science and mindful should be able to consume the same biology, physics, or other
domain definitions without copying them into application repositories.

## 2. Decision

The project family is **Nodes** and its governance identity is **nodes-dev**.

The primary distribution is named **core**, not kernel. Core includes:

- the domain-free kernel;
- the portable corpus format and shared conformance fixtures;
- structural, search, and similarity behavior;
- a small universal knowledge vocabulary suitable for both science and mindful.

Domain-specific kinds, facets, predicates, and validation rules belong in separately
publishable `nodes-<domain>` packages. The precise contents of the universal vocabulary
and the extraction of domains from science require their own designs.

### 2.1 Public name mapping

| Component | GitHub repository | npm package | PyPI distribution |
|---|---|---|---|
| Core | `nodes-dev/core` | `@nodes-dev/core` | `nodes-core` |
| Biology | initially in `nodes-dev/core` | `@nodes-dev/biology` | `nodes-biology` |
| Physics | initially in `nodes-dev/core` | `@nodes-dev/physics` | `nodes-physics` |
| Other domains | initially in `nodes-dev/core` | `@nodes-dev/<domain>` | `nodes-<domain>` |

The Python import namespace remains `nodes`. Distribution names follow PyPI's
hyphenated naming convention; import-module boundaries for independently distributed
domain packages will be decided when the first domain package is designed.

Registry checks on 2026-07-11 found the proposed core, biology, physics, chemistry,
math, and units names unpublished on npm and PyPI. Availability is not ownership: a
name is not reserved until the relevant registry resource is created.

### 2.2 Ownership

- The `nodes-dev` GitHub organization owns the repositories.
- A `nodes-dev` npm organization owns the `@nodes-dev` scope and its packages.
- A `nodes-dev` PyPI organization owns the `nodes-*` projects.
- Registry organizations have individual human owners; shared credentials are not used.
- Release workflows use trusted OIDC publishing with protected release environments.
  Long-lived npm or PyPI publication tokens are not stored in repository secrets.

Organization creation is an interactive administrative step. The npm organization is
created with its public-packages plan. The PyPI organization is requested as a community
project and is subject to PyPI approval.

### 2.3 Repository strategy

Start as a monorepo. The current repository becomes `nodes-dev/core` and remains the
authority for:

- both core language implementations;
- `docs/STANDARD.md`;
- shared cross-language fixtures;
- initially, any domain packages developed from science's existing model.

A domain moves to its own `nodes-dev/<domain>` repository only when independent
governance, substantial domain assets, or an independent release cadence makes the
monorepo materially cumbersome. Repository splitting is not required merely because a
domain has its own published package.

### 2.4 Releases and versions

`nodes-core` and `@nodes-dev/core` implement one parity contract and therefore release
in lockstep:

- one semantic version for both artifacts;
- one repository tag, such as `v0.2.0`;
- one release workflow that verifies and publishes both ecosystems;
- both artifacts publish on every core release, even when most implementation changes
  affect only one language.

Publication is all-or-nothing operationally where the registries allow it: build and
verify both artifacts before uploading either. Because two registries cannot provide a
cross-registry transaction, release automation must detect and report a partial publish
instead of silently presenting it as a complete release.

Domain packages may acquire independent versions once they exist. Their compatibility
with core must be declared through normal dependency constraints rather than by forcing
all packages in the family to share one version.

## 3. Alternatives considered

### 3.1 Keep `@nodes/kernel` and `nodes`

Rejected. The public registry identities are not controlled, `nodes` is already claimed,
and "kernel" describes only one layer of the shipped product.

### 3.2 `nodes-kernel`

Rejected. The name was available when checked, but it incorrectly implies that the
universal knowledge vocabulary is outside the primary package.

### 3.3 `nodes-plumbing`

Rejected as the primary identity. The metaphor accurately conveys infrastructure but
says less about the package-family relationship than `nodes-core` and `nodes-<domain>`.

### 3.4 `knowledge-nodes`

Rejected. It describes the product well, but produces long domain package names and
unnecessarily weakens the established Nodes identity and Python namespace.

### 3.5 Unscoped npm packages

Rejected. Names such as `nodes-core` are clean, but npm organizations cannot own
unscoped packages. The `@nodes-dev` scope aligns npm ownership with GitHub and PyPI
governance and makes the package family explicit.

### 3.6 Separate repositories immediately

Rejected. Core, language parity, fixtures, and the first vocabulary extractions will
change together. Splitting them before independent ownership or release needs emerge
would add coordination overhead without creating a useful boundary.

## 4. Consequences

- TypeScript consumers migrate from `@nodes/kernel` to `@nodes-dev/core` before the
  first public release; no compatibility package is created.
- The Python distribution changes from `nodes` to `nodes-core`, while Python imports
  remain `nodes.*`.
- Documentation and package metadata use Nodes for the project family, core for the
  primary artifact, and kernel only for the lowest architectural layer.
- The repository must be transferred or recreated under `nodes-dev/core` before trusted
  publishers are bound to its GitHub identity.
- npm and PyPI organization registration must be completed through their interactive
  administrative flows.
- Domain packages are not published as empty placeholders to reserve names.
- The base-vocabulary boundary and monorepo package layout remain deliberate follow-up
  designs; this decision does not pull science's current domain model into core.

## 5. Implementation boundary

The mechanical identity change is a separate implementation slice. It will update the
TypeScript package and lockfile names, the Python distribution name, living repository
documentation, and current downstream imports as explicitly scoped. It will not publish
packages, create registry organizations, move the Git repository, or extract domain
vocabularies without separate authorization.
