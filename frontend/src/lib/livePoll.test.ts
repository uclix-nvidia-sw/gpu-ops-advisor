import { expect, it, vi } from 'vitest';
import { useResource, type Row } from './live';
const fixture = vi.hoisted(() => ({ interval: null as unknown }));
vi.mock('@tanstack/react-query', () => ({
  useQuery: (options: Row) => {
    fixture.interval = options.refetchInterval;
    return {};
  },
  useInfiniteQuery: vi.fn(),
  useQueryClient: vi.fn(),
}));
it.each([
  [undefined, false],
  ['pending', 5000],
  ['failed', 5000],
  ['complete', false],
  ['unknown', false],
])('polls terminal report cleanup %s only while work remains', (artifact_cleanup_state, delay) => {
  useResource('/reports/saved', undefined, true);
  const interval = fixture.interval as (query: { state: Row }) => number | false;
  expect(
    interval({
      state: {
        data: {
          status: 'succeeded',
          deletion: artifact_cleanup_state ? { artifact_cleanup_state } : undefined,
        },
        error: null,
        fetchFailureCount: 0,
      },
    }),
  ).toBe(delay);
});
