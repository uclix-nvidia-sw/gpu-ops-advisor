import { createHash, webcrypto } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { randomId, sha256Hex } from './browserCrypto';
import { canonical } from './live';

afterEach(() => vi.unstubAllGlobals());

describe('HTTP browser command identifiers', () => {
  it.each(['', 'abc', '클러스터 등록 🔎', 'x'.repeat(10000)])(
    'keeps the existing SHA-256 digest without SubtleCrypto: %s',
    (value) => {
      vi.stubGlobal('crypto', {});
      expect(sha256Hex(value)).toBe(createHash('sha256').update(value, 'utf8').digest('hex'));
    },
  );

  it('finds the same pending receipt after switching from Web Crypto hashing', async () => {
    const input = canonical(['1.3', 'POST', '/clusters', { cluster_id: 'cpc-1' }]);
    const old = Buffer.from(
      await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(input)),
    ).toString('hex');
    vi.stubGlobal('crypto', { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) });
    expect(`dsx-pending-${sha256Hex(input)}`).toBe(`dsx-pending-${old}`);
    expect(sha256Hex(input)).not.toBe(
      sha256Hex(canonical(['1.3', 'POST', '/clusters', { cluster_id: 'cpc-2' }])),
    );
  });

  it('creates UUID v4 keys with HTTP-available getRandomValues only', () => {
    const random = vi.fn(webcrypto.getRandomValues.bind(webcrypto));
    vi.stubGlobal('crypto', { getRandomValues: random });
    const keys = Array.from({ length: 100 }, () => randomId());
    expect(random).toHaveBeenCalledTimes(100);
    expect(new Set(keys).size).toBe(100);
    for (const key of keys)
      expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
});
