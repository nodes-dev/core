import { FacetError, UnknownKindError } from "./errors.js";
import type { Node } from "./node.js";

export type Invariant = (node: Node) => void;

export interface KindSpec {
  name: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

export class Registry {
  private specs = new Map<string, KindSpec>();

  register(spec: KindSpec): void {
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

  validate(node: Node): void {
    const spec = this.get(node.kind);
    const required = spec.requiredFacets ?? new Set<string>();
    const optional = spec.optionalFacets ?? new Set<string>();
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
    for (const invariant of spec.invariants ?? []) {
      invariant(node);
    }
  }
}
