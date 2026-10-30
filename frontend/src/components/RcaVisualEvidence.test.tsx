import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { type Row } from '../lib/live';
import { operatorView } from '../lib/rcaOperatorView';
import { RcaOperatorReport } from './RcaOperatorReport';
import { RcaHostHistory } from './RcaHostHistory';
import { RcaHistoryChart, RcaVisualEvidence } from './RcaVisualEvidence';

const period = { start: '2026-10-30T00:00:00Z', end: '2026-10-30T00:30:00Z' };
const window = { min: 0, max: 0, last_value: 0, samples: 2, first: period.start, last: period.end };
function result(metrics: Row[] = [], overrides: Row = {}) {
  return {
    quality: {
      triage_observations: {
        schema: 'rca-triage-observations/1',
        period,
        target: { node: 'node-a', title: 'XID 96 PCI:0000:07:00' },
        event_boundary: '2026-10-30T00:20:00Z',
        metrics,
        ...overrides,
      },
    },
  };
}
function visual(value: Row) {
  return renderToStaticMarkup(<RcaVisualEvidence view={operatorView(value)!} />);
}

it('keeps zero, missing windows and sample counts distinct without changing saved results', () => {
  const value = result([
    {
      name: '사용률',
      query: 'D01',
      unit: 'percent',
      kind: 'gauge',
      incident_windows: { before: window },
    },
  ]);
  const saved = JSON.stringify(value);
  const html = visual(value);
  expect(html).toContain('<strong>0 %</strong>');
  expect(html).toContain('2개 표본');
  expect(html).toContain('<span>사건 후</span><strong>표본 없음·확인 불가</strong>');
  expect(html).not.toContain('class="c2-rca-range"');
  expect(html).not.toContain('NaN');
  expect(JSON.stringify(value)).toBe(saved);
});

it('does not draw numeric ranges for enum states or invent before/after for whole-window data', () => {
  const html = visual(
    result([{ name: '상태', query: 'D01', unit: 'enum', kind: 'enum', ...window }]),
  );
  expect(html).toContain('조회 구간 전체');
  expect(html).toContain('사건 전후로 나뉘지 않은 저장값');
  expect(html).not.toContain('class="c2-rca-range"');
  expect(html).not.toContain('정상');
});

it('rejects invalid ranges and missing last values instead of putting them at zero', () => {
  for (const bad of [
    { min: 3, max: 1, last_value: 2 },
    { last_value: undefined },
    { min: NaN },
    { samples: 0 },
  ]) {
    const html = visual(
      result([
        {
          name: '전력',
          query: 'D01',
          unit: 'W',
          kind: 'gauge',
          incident_windows: { after: { ...window, ...bad } },
        },
      ]),
    );
    expect(html).not.toContain('class="c2-rca-range"');
    expect(html).not.toContain('NaN');
    expect(html).toContain('표본 없음·확인 불가');
  }
});

it('labels an observed-range axis and keeps cumulative counters on a zero-based axis', () => {
  const metric = {
    name: '전력',
    query: 'D01',
    unit: 'W',
    kind: 'gauge',
    incident_windows: { before: { ...window, min: 79, max: 81, last_value: 80 } },
  };
  expect(visual(result([metric]))).toContain('관측 범위에 맞춘 축');
  const counter = visual(result([{ ...metric, kind: 'counter', unit: 'count' }]));
  expect(counter).not.toContain('관측 범위에 맞춘 축');
  expect(counter).toContain('이번 사건의 발생 건수가 아닙니다');
});

it('keeps out-of-period and absent times explicit and does not draw an invalid time axis', () => {
  const logs = [
    {
      code: 'xid:96',
      device: '0000:07:00',
      first: '2026-10-29T23:59:00Z',
      last: '2026-10-30T00:10:00Z',
      reports: 2,
    },
  ];
  expect(visual(result([], { logs }))).toContain('구간 밖');
  const html = visual(result([], { period: { start: 'invalid', end: period.end } }));
  expect(html).toContain('유효한 조회 구간이 없어');
  expect(html).toContain('시각 미기록');
  expect(html).not.toContain('class="c2-rca-timeline"');
  expect(html).toContain('비교할 지표가 저장되지 않았습니다');
});

it('adds the visuals only to the console 2 report', () => {
  expect(renderToStaticMarkup(<RcaOperatorReport result={result()} />)).not.toContain(
    'c2-rca-visual',
  );
  expect(renderToStaticMarkup(<RcaOperatorReport result={result()} decisionSummary />)).toContain(
    'id="c2-rca-visual"',
  );
});

it('counts distinct incident IDs by KST day within exact bounds, including partial history', () => {
  const incidents = [
    { incident_id: 'a', occurred_at: '2026-10-29T15:01:00Z' },
    { incident_id: 'a', occurred_at: '2026-10-29T15:01:00Z' },
    { incident_id: 'b', occurred_at: '2026-10-30T00:31:00Z' },
    { incident_id: 'c', occurred_at: 'invalid' },
  ];
  const html = renderToStaticMarkup(
    <RcaHistoryChart
      incidents={incidents}
      start={Date.parse('2026-10-29T15:00:00Z')}
      end={Date.parse(period.end)}
      complete={false}
    />,
  );
  expect(html).toContain('선택 조건 1건');
  expect(html).toContain('2026-10-30: 1건');
  expect(html).toContain('일부 이력만 저장');
  expect(html).not.toContain('2026-10-29:');
});

it('uses the same device/code filter for the history chart and incident table', () => {
  const value = {
    quality: {
      host_incident_history: {
        schema: 'rca-host-history/1',
        complete: true,
        period,
        rows: [
          {
            incident_id: 'a',
            occurred_at: period.start,
            codes: ['xid:96'],
            device: 'gpu-a',
            current: true,
          },
          { incident_id: 'b', occurred_at: period.start, codes: ['xid:95'], device: 'gpu-b' },
        ],
      },
    },
  };
  expect(renderToStaticMarkup(<RcaHostHistory result={value} embedded visual />)).toContain(
    '선택 조건 1건',
  );
  expect(renderToStaticMarkup(<RcaHostHistory result={value} visual />)).toContain('선택 조건 2건');
  expect(renderToStaticMarkup(<RcaHostHistory result={value} />)).not.toContain('날짜별 등록 사건');
});

it('collapses identical timestamps while preserving each source and keeps distinct times on a timeline', () => {
  const view = operatorView(result())!;
  const shared = '2026-10-30T00:20:00Z';
  const same = {
    ...view,
    eventTime: shared,
    firstReport: shared,
    lastReport: shared,
    boundary: shared,
  };
  const html = renderToStaticMarkup(<RcaVisualEvidence view={same} />);
  expect(html).toContain('공통 기준 시각');
  expect(html).toContain('시각 근거 보기');
  const missingPeriod = renderToStaticMarkup(
    <RcaVisualEvidence view={{ ...same, periodStart: '', periodEnd: '' }} />,
  );
  expect(missingPeriod).not.toContain('조회 구간 밖');
  expect(missingPeriod).toContain('유효한 조회 구간이 없어');
  expect(html).not.toContain('class="c2-rca-timeline"');
  expect(
    renderToStaticMarkup(<RcaVisualEvidence view={{ ...same, firstReport: period.start }} />),
  ).toContain('class="c2-rca-timeline"');
});
