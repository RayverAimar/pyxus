import type {
  GraphData,
  SearchResponse,
  ImportsResponse,
} from "../types/graph";

const BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

/** Fetch the full graph or a filtered view. */
export function fetchGraph(level?: "module"): Promise<GraphData> {
  const params = level ? `?level=${level}` : "";
  return fetchJSON<GraphData>(`/graph${params}`);
}

/** Search symbols by name. */
export function searchSymbols(
  query: string,
  limit = 10
): Promise<SearchResponse> {
  return fetchJSON<SearchResponse>(
    `/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
}

/** Fetch import dependencies and circular imports. */
export function fetchImports(): Promise<ImportsResponse> {
  return fetchJSON<ImportsResponse>("/imports");
}

/** Fetch context for a symbol by name. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fetchContext(name: string): Promise<any> {
  return fetchJSON(`/context/${encodeURIComponent(name)}`);
}
