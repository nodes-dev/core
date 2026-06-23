export class NodesError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class IdError extends NodesError {}
export class RefError extends NodesError {}
export class CollisionError extends NodesError {}
export class UnknownKindError extends NodesError {}
export class FacetError extends NodesError {}
export class InvariantError extends NodesError {}
export class ValidationError extends NodesError {}
export class EmbedderRequiredError extends NodesError {}
