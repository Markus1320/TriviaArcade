// Typed client for the backend API.

export type ComponentStatus = 'ok' | 'error';

export interface HealthResponse {
  status: ComponentStatus;
  postgres: ComponentStatus;
  neo4j: ComponentStatus;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return ['status', 'postgres', 'neo4j'].every(
    (key) => record[key] === 'ok' || record[key] === 'error',
  );
}

// The health endpoint answers 503 with a valid body when a database is down,
// so the body is parsed regardless of the status code.
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal });
  const body: unknown = await response.json();
  if (!isHealthResponse(body)) {
    throw new Error(`Unexpected health response (HTTP ${String(response.status)})`);
  }
  return body;
}
