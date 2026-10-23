import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test } from 'vitest';
import { RcaHostHistory } from './RcaHostHistory';
import { RcaTriageObservations } from './RcaTriageObservations';

test('host history shows stored incident IDs, periods and detail links', () => {
  const result = {
    quality: {
      host_incident_history: {
        schema: 'rca-host-history/1',
        complete: true,
        period: { start: '2026-10-07T00:00:00Z', end: '2026-10-21T00:00:00Z' },
        rows: [
          {
            incident_id: 'a',
            occurred_at: '2026-10-20T00:00:00Z',
            first_report: '2026-10-20T00:00:00Z',
            last_report: '2026-10-20T00:10:00Z',
            reported_span_seconds: 600,
            codes: ['xid:48'],
            reason: '<script>bad</script>',
          },
        ],
      },
    },
  };
  const html = renderToStaticMarkup(<RcaHostHistory result={result} />);
  expect(html).toContain('등록 사건 1건');
  expect(html).toContain('10분 관측');
  expect(html).toContain('/incidents/a');
  expect(html).toContain('최근 7일');
  expect(html).not.toContain('<script>');
  expect(JSON.stringify(result)).toContain('<script>bad</script>');
});

test('old reports do not invent history or metrics', () => {
  expect(renderToStaticMarkup(<RcaHostHistory result={{}} />)).toBe('');
  expect(renderToStaticMarkup(<RcaTriageObservations result={{}} />)).toBe('');
});

test('metric table preserves zero, units and node context', () => {
  const html = renderToStaticMarkup(
    <RcaTriageObservations
      result={{
        quality: {
          triage_observations: {
            schema: 'rca-triage-observations/1',
            target: { node: 'node-a' },
            period: {},
            logs: [],
            metric_scope: 'node_gpu_context',
            metrics: [
              {
                name: 'NVLink 수신량',
                min: 0,
                max: 4,
                last_value: 0,
                unit: 'bytes_per_second',
                samples: 2,
              },
            ],
          },
        },
      }}
    />,
  );
  expect(html).toContain('GPU별 지표');
  expect(html).toContain('조회 구간 0 B/s ~ 4 B/s');
  // Results stored before pod labels existed do not claim that no pod was running.
  expect(html).not.toContain('파드가 없습니다');
});

test('repeat intervals group the same code and device and mark the query boundary', () => {
  const makeRow = (id: string, day: number, gpu: string) => ({
    incident_id: id,
    occurred_at: `2026-10-${day}T00:00:00Z`,
    codes: ['xid:79'],
    gpu_uuid: gpu,
    last_report_capped: true,
  });
  const html = renderToStaticMarkup(
    <RcaHostHistory
      result={{
        quality: {
          host_incident_history: {
            schema: 'rca-host-history/1',
            complete: true,
            period: { start: '2026-10-07T00:00:00Z', end: '2026-10-21T00:00:00Z' },
            rows: [makeRow('a', 20, 'GPU-A'), makeRow('b', 18, 'GPU-A'), makeRow('c', 19, 'GPU-B')],
          },
        },
      }}
    />,
  );
  expect(html).toContain('XID:79 · 호스트 전체</td><td>3건');
  expect(html).toContain('XID:79 · GPU-A</summary>');
  expect(html).toContain('코드·대상별 등록 건수와 최근 간격');
  expect(html).toContain('XID:79 · GPU-A');
  expect(html).toContain('<td>2.0일</td>');
  expect(html).not.toContain('GPU-B · 2건');
  expect(html).toContain('(조회 종료)');
});
