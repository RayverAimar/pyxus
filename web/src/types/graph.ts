/** Symbol kinds matching Python backend SymbolKind enum. */
export type SymbolKind =
  | "module"
  | "class"
  | "function"
  | "method"
  | "property"
  | "classmethod"
  | "staticmethod";

/** Relationship kinds matching Python backend RelationKind enum. */
export type RelationKind =
  | "defines"
  | "has_method"
  | "calls"
  | "imports"
  | "extends";

/** A graph node as returned by GET /api/graph. */
export interface GraphNode {
  id: string;
  label: string;
  kind: SymbolKind;
  file: string;
  line: number;
  endLine: number;
  decorators: string[];
  isExported: boolean;
  size: number;
  degree: number;
}

/** A graph edge as returned by GET /api/graph. */
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: RelationKind;
  confidence: number;
  metadata?: Record<string, unknown>;
}

/** Stats included in the graph response. */
export interface GraphStats {
  nodeCount: number;
  edgeCount: number;
  callResolutionRate?: number;
  indexedAt?: string;
  filesIndexed?: number;
}

/** Full response from GET /api/graph. */
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

/** A search result from GET /api/search. */
export interface SearchResult {
  name: string;
  kind: SymbolKind;
  file: string;
  line: number;
  score: number;
}

/** Response from GET /api/search. */
export interface SearchResponse {
  query: string;
  total_matches: number;
  results: SearchResult[];
}


/** Response from GET /api/imports. */
export interface ImportsResponse {
  total_modules: number;
  total_dependencies: number;
  circular_imports: string[][];
  modules: {
    file: string;
    name: string;
    imports: number;
    imported_by: number;
  }[];
}
