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
  expect(html).toContain('<strong>XID:79 · 호스트 전체</strong></td><td>3건');
  // Device rows sit under their code's host row, busiest first, without a repeating toggle.
  expect(html.indexOf('GPU-A</td><td>2건')).toBeLessThan(html.indexOf('GPU-B</td><td>1건'));
  expect(html).not.toContain('<summary>XID:79');
  expect(html).toContain('코드·대상별 등록 건수와 최근 간격');
  expect(html).toContain('<td>2.0일</td>');
  expect(html).not.toContain('GPU-B · 2건');
  expect(html).toContain('(조회 종료)');
});

test('device rows stay under their own code, the current alert code first', () => {
  const row = (id: string, day: number, code: string, device: string) => ({
    incident_id: id,
    occurred_at: `2026-10-${day}T00:00:00Z`,
    codes: [code],
    device,
    current: id === 'a',
  });
  // Incidents interleave codes; grouping must not follow first appearance.
  const result = {
    quality: {
      host_incident_history: {
        schema: 'rca-host-history/1',
        complete: true,
        period: { start: '2026-10-07T00:00:00Z', end: '2026-10-21T00:00:00Z' },
        rows: [
          row('a', 20, 'sxid:11001', 'NVSwitch PCI:0000:c4:00.0'),
          row('b', 19, 'xid:79', 'GPU-X'),
          row('c', 18, 'sxid:11001', 'NVSwitch PCI:0000:c7:00.0'),
        ],
      },
    },
  };
  const all = renderToStaticMarkup(<RcaHostHistory result={result} />);
  const at = (s: string) => all.indexOf(s);
  expect(at('SXID:11001 · 호스트 전체')).toBeLessThan(at('0000:c7:00.0'));
  expect(at('0000:c7:00.0')).toBeLessThan(at('XID:79 · 호스트 전체'));
  expect(at('XID:79 · 호스트 전체')).toBeLessThan(at('GPU-X</td>'));
  expect(all).toContain('이번 장치');
  // The embedded report starts on the same device and code, as before: no host rows.
  const related = renderToStaticMarkup(<RcaHostHistory result={result} embedded />);
  expect(related).not.toContain('호스트 전체');
  expect(related).not.toContain('GPU-X');
  expect(related).toContain('SXID:11001 · ');
});
