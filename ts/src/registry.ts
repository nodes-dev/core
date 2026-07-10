import { FacetError, InvariantError, UnknownKindError, ValidationError } from "./errors.js";
import type { Node } from "./node.js";

export type Invariant = (node: Node) => void;

export interface ShapeSpec {
  name: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

export interface KindSpec {
  name: string;
  shape?: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

/** One structured validation finding from `Registry.check` (never thrown). */
export interface Violation {
  readonly code: string;
  readonly detail: string;
  readonly message: string;
}

export class Registry {
  private specs = new Map<string, KindSpec>();
  private shapes = new Map<string, ShapeSpec>();

  registerShape(spec: ShapeSpec): void {
    if (this.shapes.has(spec.name)) {
      throw new ValidationError(`shape ${JSON.stringify(spec.name)} is already registered`);
    }
    this.shapes.set(spec.name, spec);
  }

  isShape(name: string): boolean {
    return this.shapes.has(name);
  }

  register(spec: KindSpec): void {
    if (this.specs.has(spec.name)) {
      throw new ValidationError(`kind ${JSON.stringify(spec.name)} is already registered`);
    }
    if (spec.shape !== undefined && !this.shapes.has(spec.shape)) {
      throw new UnknownKindError(
        `kind ${JSON.stringify(spec.name)} adopts unknown shape ${JSON.stringify(spec.shape)}`,
      );
    }
    this.specs.set(spec.name, spec);
  }

  isRegistered(kind: string): boolean {
    return this.specs.has(kind);
  }

  get(kind: string): KindSpec {
    const spec = this.specs.get(kind);
    if (spec === undefined) {
      throw new UnknownKindError(`kind ${JSON.stringify(kind)} is not registered`);
    }
    return spec;
  }

  private compose(
    spec: KindSpec,
    kind: string,
  ): { required: Set<string>; optional: Set<string>; invariants: Invariant[] } {
    const required = new Set(spec.requiredFacets ?? []);
    const optional = new Set(spec.optionalFacets ?? []);
    const invariants: Invariant[] = [];
    if (spec.shape !== undefined) {
      const shape = this.shapes.get(spec.shape);
      if (shape === undefined) {
        throw new UnknownKindError(`kind ${JSON.stringify(kind)} adopts unknown shape ${JSON.stringify(spec.shape)}`);
      }
      for (const f of shape.requiredFacets ?? []) required.add(f);
      for (const f of shape.optionalFacets ?? []) optional.add(f);
      for (const inv of shape.invariants ?? []) invariants.push(inv);
    }
    for (const inv of spec.invariants ?? []) invariants.push(inv);
    return { required, optional, invariants };
  }

  validate(node: Node): void {
    const spec = this.get(node.kind);
    const { required, optional, invariants } = this.compose(spec, node.kind);
    const present = new Set(Object.keys(node.facets));
    const missing = [...required].filter((f) => !present.has(f)).sort();
    if (missing.length > 0) {
      throw new FacetError(`${node.id}: missing required facets ${JSON.stringify(missing)}`);
    }
    const allowed = new Set([...required, ...optional]);
    const unexpected = [...present].filter((f) => !allowed.has(f)).sort();
    if (unexpected.length > 0) {
      throw new FacetError(`${node.id}: unexpected facets ${JSON.stringify(unexpected)}`);
    }
    for (const invariant of invariants) invariant(node);
  }

  /** Collect ALL violations of `node` with machine-stable codes; never throws on
   * content. Non-kernel exceptions from invariants are programmer bugs and propagate. */
  check(node: Node): Violation[] {
    const spec = this.specs.get(node.kind);
    if (spec === undefined) {
      return [
        {
          code: "unknown-kind",
          detail: node.kind,
          message: `${node.id}: kind ${JSON.stringify(node.kind)} is not registered`,
        },
      ];
    }
    const { required, optional, invariants } = this.compose(spec, node.kind);
    const present = new Set(Object.keys(node.facets));
    const violations: Violation[] = [];
    for (const name of [...required].filter((f) => !present.has(f)).sort()) {
      violations.push({
        code: "facet-missing",
        detail: name,
        message: `${node.id}: missing required facet ${JSON.stringify(name)}`,
      });
    }
    const allowed = new Set([...required, ...optional]);
    for (const name of [...present].filter((f) => !allowed.has(f)).sort()) {
      violations.push({
        code: "facet-unexpected",
        detail: name,
        message: `${node.id}: unexpected facet ${JSON.stringify(name)}`,
      });
    }
    // Invariants presuppose their facets; running them anyway would duplicate reports.
    if (violations.length > 0) return violations;
    for (const invariant of invariants) {
      try {
        invariant(node);
      } catch (exc) {
        if (exc instanceof FacetError) {
          violations.push({ code: "facet-invalid", detail: "", message: exc.message });
        } else if (exc instanceof InvariantError) {
          violations.push({ code: "invariant-violated", detail: "", message: exc.message });
        } else {
          throw exc;
        }
      }
    }
    return violations;
  }
}
