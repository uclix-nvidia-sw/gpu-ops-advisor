import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { differences, DifferenceTable } from './TraceView';
import { RunbookContent } from './RunbookContent';
import runbook from '../../../rcca-agent/runbooks/xid/RB-XID-99.json';
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
