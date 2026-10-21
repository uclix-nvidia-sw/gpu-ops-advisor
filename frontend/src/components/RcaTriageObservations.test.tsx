import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaTriageObservations } from './RcaTriageObservations';
import { RcaNarrative } from './RcaNarrative';

const metric = {
  name: 'NVLink RX',
  unit: 'bytes/s',
  min: 0,
  max: 0,
  last_value: 0,
  first: '2026-10-21T06:00:00Z',
  last: '2026-10-21T06:10:00Z',
  samples: 13,
};
const result = {
  quality: {
    report: { presentation: 'incident-first/2' },
    triage_observations: {
      schema: 'rca-triage-observations/1',
      target: { node: 'dgx02' },
      logs: [{ code: 'sxid:11001', first: metric.first, last: metric.last, reports: 6 }],
      metrics: [
        { ...metric, gpu_uuid: 'GPU-A' },
        { ...metric, gpu_uuid: 'GPU-B' },
        { ...metric, gpu_uuid: 'GPU-C', max: 1 },
      ],
    },
  },
  narrative: [
    { id: 'comparison', title: '비교 상세', text: '저장된 비교 원문' },
    { id: 'action', title: '권고 조치', text: '진단 자료 보존' },
    { id: 'cause', title: '분석 결과', text: '기록에 근거한 결론' },
  ],
};
it('groups identical summaries without hiding different measurements or GPU identities', () => {
  const html = renderToStaticMarkup(<RcaTriageObservations result={result} />);
  expect(html.match(/NVLink RX/g)).toHaveLength(2);
  expect(html).toContain('GPU 2개');
  for (const gpu of ['GPU-A', 'GPU-B', 'GPU-C']) expect(html).toContain(gpu);
});
it('leads with the incident and recommendations, keeps comparisons and evaluation secondary', () => {
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(html.indexOf('1. 사건 요약')).toBeLessThan(html.indexOf('2. 분석 결과'));
  expect(html.indexOf('진단 자료 보존')).toBeLessThan(html.indexOf('사건 로그와 관련 지표'));
  expect(html).not.toContain('분석 처리:');
  expect(html.indexOf('사건 로그와 관련 지표')).toBeLessThan(html.indexOf('5. 조사'));
  expect(html).toContain('<summary>비교 상세</summary>');
  expect(html).toContain('저장된 비교 원문');
  expect(JSON.stringify(result)).toBe(before);
});

it('renders enum codes without treating them as numeric ranges or health', () => {
  const value = {
    quality: {
      triage_observations: {
        schema: 'rca-triage-observations/1',
        metrics: [{ ...metric, name: 'FM', unit: 'enum' }],
      },
    },
  };
  const html = renderToStaticMarkup(<RcaTriageObservations result={value} />);
  expect(html).toContain('상태 코드 0 · 관측 내 변화 없음');
  expect(html).not.toContain('최소');
  expect(html).not.toContain('마지막 값');
  expect(html).not.toContain('정상');
});
