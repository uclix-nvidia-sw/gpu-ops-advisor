/** Production transport foundation. Demo UI uses demoRepository until backend integration. */
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
  const response = await fetch(`/api/v1${path}`, {
    method: options.method || 'GET',
    headers,
    credentials: 'same-origin',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  const body = await response.json();
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
