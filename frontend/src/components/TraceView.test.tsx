import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { differences, DifferenceTable, StoredEvidence } from './TraceView';
import { RunbookContent } from './RunbookContent';
// Snapshot of rcca-agent/runbooks/xid/RB-XID-99.json, kept inside the frontend build context.
import runbook from './fixtures/RB-XID-99.json';
import { evidenceRelation, jobRelation } from '../lib/debug';

describe('stored web trace', () => {
  it('preserves missing vs null and microsecond differences', () => {
    const a = { input: { end: '2026-09-30T08:07:48.122307Z', count: 0, missing: null } };
    const b = { input: { end: '2026-09-30T08:07:48.122Z', count: 0 } };
    expect(differences(a, b).map((d) => d.path)).toEqual(['input.end', 'input.missing']);
    const html = renderToStaticMarkup(<DifferenceTable left={a} right={b} />);
    expect(html).toContain('.122307Z');
    expect(html).toContain('필드 없음');
  });
  it('shows the real XID 99 content without requiring legacy content.text', () => {
    const html = renderToStaticMarkup(<RunbookContent value={runbook.content} />);
    expect(html).toContain('NVJPG1 Error');
    expect(html).toContain('적용 조건');
    expect(html).toContain('D09');
    expect(html).toContain('content 원본 JSON');
    expect(
      renderToStaticMarkup(
        <RunbookContent value={{ title: 'legacy', text: '<script>hello</script>' }} />,
      ),
    ).not.toContain('<script>hello');
  });
  it('uses the pinned incident revision and binds evidence reads to a selected attempt', () => {
    const trace = {
      incident_id: 'i1',
      evidence_version: 2,
      incident_snapshot: {
        state: 'available',
        record: { incident_id: 'i1', revision: 2, snapshot: { input: {} } },
      },
    };
    const relation = jobRelation({ id: 'j1', incident_id: 'i1' }, 'snapshot', 1, trace);
    expect(relation.record?.revision).toBe(2);
    expect(relation.unavailable).toBeUndefined();
    expect(evidenceRelation({ id: 'j1', attempt_no: 1 }, 'e1', true).path).toBe(
      '/jobs/j1/evidence/e1?attempt=1',
    );
  });
});

vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: () => ({
    items: [
      {
        id: 'actual',
        query_id: 'D09',
        tool_status: 'ok',
        created_at: '2026-10-02T05:00:00Z',
        recorded_at: '2026-10-02T04:41:37.229202Z',
        order_basis: 'recorded_time',
      },
      {
        id: 'legacy',
        query_id: 'D05',
        tool_status: 'ok',
        created_at: '2026-10-02T05:00:00Z',
        order_basis: 'inferred_plan',
      },
      {
        id: 'unknown',
        query_id: 'custom',
        tool_status: 'ok',
        created_at: '2026-10-02T05:00:00Z',
        order_basis: 'unknown',
      },
    ],
    isPending: false,
    isError: false,
    hasNextPage: false,
  }),
}));

it('distinguishes actual KST record time from legacy inferred order without reordering API rows', () => {
  const html = renderToStaticMarkup(
    <StoredEvidence job={{ id: 'job' }} attempt={1} onEvidence={() => {}} />,
  );
  expect(html).toContain('13:41:37');
  expect(html).toContain('.229202');
  expect(html).toContain('기록 생성 시각');
  expect(html).toContain('계획 기반 추정 순서');
  expect(html).toContain('실행 순서 미확인');
  expect(html.indexOf('actual')).toBeLessThan(html.indexOf('legacy'));
  expect(html).toContain('2026-10-02T04:41:37.229202Z');
});
