export {
  CollisionError,
  EmbedderRequiredError,
  FacetError,
  IdError,
  InvariantError,
  NodesError,
  RefError,
  UnknownKindError,
  ValidationError,
} from "./errors.js";
export { NodeId, type Ref } from "./ids.js";
export {
  RELATES_TO,
  RelationSchema,
  type Relation,
  fromSerialized,
  relatesTo,
  tagToRelation,
  toSerialized,
} from "./relations.js";
export {
  NodeMetadataSchema,
  NodeSchema,
  type Node,
  type NodeInput,
  type NodeMetadata,
  makeNode,
  newUid,
} from "./node.js";
export { nodeFromMarkdown, nodeToMarkdown, splitFrontmatter } from "./frontmatter.js";
export { type Invariant, type KindSpec, type ShapeSpec, Registry } from "./registry.js";
export {
  EDGES,
  EdgesSchema,
  KEYS,
  KeysSchema,
  MEMBERSHIP,
  MembershipSchema,
  ORDER,
  OrderSchema,
  edgesOf,
  keysOf,
  membershipOf,
  orderOf,
  registerBuiltinShapes,
  requireAcyclic,
  requireEdgeEndpointsAreMembers,
  requireKeyValuesAreMembers,
  requireOrderIsPermutation,
  requireSingleParent,
  requireUniqueMembers,
} from "./shapes.js";
export type { Edges, Keys, Membership, Order } from "./shapes.js";
export { Store } from "./store.js";
export { Corpus } from "./corpus.js";
export {
  type CorpusFile,
  type CorpusFileStat,
  type CorpusFingerprint,
  type ManifestEntry,
  type Snapshot,
  SNAPSHOT_LANG,
  SNAPSHOT_SCHEMA_VERSION,
  hashBytes,
  iterCorpusFiles,
  listCorpusFileStats,
  loadSnapshot,
  pathForNodeId,
  readCorpusFingerprint,
  readJson,
  sameCorpusFingerprint,
  snapshotPath,
  writeJsonAtomic,
  writeSnapshot,
} from "./snapshot.js";
export {
  Index,
  type InRef,
  type IndexEntry,
  type OutRef,
  type ResolvedEdge,
  type Role,
} from "./structural-index.js";
export { scoreKey } from "./ranking.js";
export { SearchIndex, type SearchHit, type SearchSnapshot, tokenize } from "./search.js";
export {
  type Embedder,
  type SimilarHit,
  type Vector,
  type VectorSnapshot,
  VectorCache,
  VectorIndex,
  embedText,
  textHash,
  validateNamespace,
  validateTextHash,
} from "./similarity.js";
