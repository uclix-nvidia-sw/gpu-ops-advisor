import { describe, expect, it, vi, afterEach } from 'vitest';
import { preciseRange, formatDate } from './domain';
import { canonical } from './live';
import { apiRequest, ApiError } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('live API boundary', () => {
  it('converts KST inputs to exclusive UTC intervals and does not invent dates', () => {
    expect(preciseRange('2026-09-17T09:00', '2026-09-17T10:00')).toEqual({
      start: '2026-09-17T00:00:00.000Z',
      end: '2026-09-17T01:00:00.000Z',
    });
    expect(() => preciseRange('2026-09-17T10:00', '2026-09-17T09:00')).toThrow();
    expect(formatDate('')).toBe('—');
  });
  it('makes retry fingerprints stable across object property order', () => {
    expect(canonical({ b: 2, a: { z: 1, y: 2 } })).toBe(canonical({ a: { y: 2, z: 1 }, b: 2 }));
    expect(canonical({ a: 1 })).not.toBe(canonical({ a: 2 }));
  });
  it('sends preconditions and idempotency keys, and surfaces module errors', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { message: '담당 모듈이 연결되지 않았습니다.' },
          request_id: 'request-1',
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetcher);
    await expect(
      apiRequest('/jobs/job-1/cancel', {
        method: 'POST',
        body: { reason: '중단' },
        version: 7,
        idempotencyKey: 'retry-key',
      }),
    ).rejects.toMatchObject({ status: 503, requestId: 'request-1' } satisfies Partial<ApiError>);
    expect(fetcher).toHaveBeenCalledWith(
      '/api/v1/jobs/job-1/cancel',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'If-Match': '"7"', 'Idempotency-Key': 'retry-key' }),
        body: '{"reason":"중단"}',
      }),
    );
  });
});
