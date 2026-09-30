/** Same-origin transport for the Go API. */
export type ApiTrace = {
  id: number;
  method: string;
  path: string;
  status: number;
  duration: number;
  requestId: string;
  at: string;
};
let traces: ApiTrace[] = [];
let traceId = 0;
const traceListeners = new Set<() => void>();
export const apiTraceSnapshot = () => traces;
export function subscribeApiTrace(listener: () => void) {
  traceListeners.add(listener);
  return () => {
    traceListeners.delete(listener);
  };
}
export function clearApiTrace() {
  traces = [];
  traceListeners.forEach((listener) => listener());
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
    public details?: Record<string, unknown>,
    public retryAfter?: string | null,
  ) {
    super(message);
  }
}
export async function apiRequest<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    version?: number;
    idempotencyKey?: string;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (options.version !== undefined) headers['If-Match'] = `"${options.version}"`;
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method || 'GET',
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) recordTrace(0);
    throw error;
  }
  function recordTrace(status: number, requestId = '') {
    // Keep only transport metadata, never bodies, query values, credentials or model output.
    traces = [
      {
        id: ++traceId,
        method: options.method || 'GET',
        path: path.split('?')[0],
        status,
        duration: Math.round(performance.now() - started),
        requestId,
        at: new Date().toISOString(),
      },
      ...traces,
    ].slice(0, 50);
    traceListeners.forEach((listener) => listener());
  }
  if (!response.headers.get('Content-Type')?.includes('application/json')) {
    recordTrace(response.status);
    throw new ApiError(
      response.status,
      '백엔드 응답을 확인할 수 없습니다. 서버 연결을 확인해 주세요.',
    );
  }
  let body;
  try {
    body = await response.json();
  } catch (error) {
    recordTrace(response.status);
    throw error;
  }
  recordTrace(response.status, typeof body.request_id === 'string' ? body.request_id : '');
  if (!response.ok)
    throw new ApiError(
      response.status,
      body.error?.message || '요청을 처리하지 못했습니다.',
      body.request_id,
      body.error?.details,
      response.headers.get('Retry-After'),
    );
  return body as T;
}
