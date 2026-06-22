import { IdError } from "./errors.js";

export type Ref = string;

const KIND_RE = /^[a-z][a-z0-9-]*$/;
const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9:_.-]*$/;

export class NodeId {
  constructor(
    readonly kind: string,
    readonly slug: string,
  ) {}

  static isValidKind(kind: string): boolean {
    return KIND_RE.test(kind);
  }

  static isValidSlug(slug: string): boolean {
    return SLUG_RE.test(slug);
  }

  static parse(raw: string): NodeId {
    const idx = raw.indexOf(":");
    if (idx === -1) {
      throw new IdError(`id must be 'kind:slug', got ${JSON.stringify(raw)}`);
    }
    const kind = raw.slice(0, idx);
    const slug = raw.slice(idx + 1);
    if (!NodeId.isValidKind(kind)) {
      throw new IdError(`invalid kind ${JSON.stringify(kind)} in id ${JSON.stringify(raw)}`);
    }
    if (!NodeId.isValidSlug(slug)) {
      throw new IdError(`invalid slug ${JSON.stringify(slug)} in id ${JSON.stringify(raw)}`);
    }
    return new NodeId(kind, slug);
  }

  toString(): string {
    return `${this.kind}:${this.slug}`;
  }
}
