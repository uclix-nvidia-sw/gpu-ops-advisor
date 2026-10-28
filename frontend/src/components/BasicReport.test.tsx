import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { BasicReport, lowActivityBands, operationalFindings, ReportChecks } from './BasicReport';
import { ReportContent } from './ReportContent';

const start = '2026-10-12T00:00:00Z';
const end = '2026-10-12T01:00:00Z';
const target = { cluster_id: 'test', namespace: 'training', model: 'A100' };

it('prioritizes actionable checks and preserves incident uncertainty and evidence links', () => {
  const topics = [
    {
      topic_id: 'O05',
      findings: [
        {
          id: 'event-1',
          priority: 2,
          text: '저장된 장애 사건',
          next_check: '조사 결과와 실제 조치 기록을 확인하세요.',
          incident_id: 'event-id',
          alarm_status: 'resolved',
          rca_result_ids: ['rca-id'],
          action_record_ids: [],
          status_as_of: end,
          target,
          period: { start, end },
          evidence_refs: ['proof-id'],
        },
      ],
    },
    {
      topic_id: 'O08',
      findings: [
        {
          id: 'low-1',
          priority: 1,
          text: 'GPU 1대의 연속 저활동',
          next_check: '해당 시간대 작업 목적을 확인하세요.',
          target,
          period: { start, end },
        },
        { id: 'legacy', text: '과거 판단 형식' },
      ],
    },
  ];
  expect(operationalFindings(topics).map((finding) => finding.id)).toEqual(['low-1', 'event-1']);
  const html = renderToStaticMarkup(
    <ReportContent onEvidence={() => {}} value={{ versions: { criteria: '1.3' }, topics }} />,
  );
  expect(html.indexOf('먼저 확인할 내용')).toBeLessThan(html.indexOf('분석 범위와 자료 상태'));
  expect(html).toContain('다음 확인');
  expect(html).toContain('href="/incidents/event-id"');
  expect(html).toContain('해제 알림 수신');
  expect(html).toContain('1건 연결됨');
  expect(html).toContain('연결된 조치 기록 없음 · 미수행 확정 아님');
  expect(html).toContain('10. 12. 10:00 기준');
  expect(html).not.toContain('조치 완료');
  expect(html).not.toContain('href="/analyses/');
  expect(html).toContain('근거 1');
});

it('keeps more than five findings available and legacy results unchanged', () => {
  const html = renderToStaticMarkup(
    <ReportChecks
      onEvidence={() => {}}
      topics={[
        {
          topic_id: 'O08',
          findings: Array.from({ length: 7 }, (_, i) => ({
            id: `f${i}`,
            text: `대상 ${i}`,
            next_check: `확인 ${i}`,
            priority: i,
          })),
        },
      ]}
    />,
  );
  expect(html).toContain('나머지 확인 사항 2개');
  expect(html).toContain('<ol start="6">');
  expect(
    renderToStaticMarkup(
      <ReportChecks
        onEvidence={() => {}}
        topics={[{ topic_id: 'O03', findings: [{ id: 'legacy', text: '기존 저장 판단' }] }]}
      />,
    ),
  ).toBe('');
});

it('shades only stored GPU low-activity intervals, preserving actual time gaps', () => {
  const interval = (a: string, b: string, value: number | null = 1800) => ({
    value,
    period: { start: a, end: b },
  });
  const bands = lowActivityBands([
    interval(start, '2026-10-12T00:40:00Z'),
    interval('2026-10-12T00:20:00Z', end),
    interval('2026-10-12T01:15:00Z', '2026-10-12T01:45:00Z'),
    interval(end, '2026-10-12T01:15:00Z', null),
    interval('invalid', end),
  ]);
  expect(bands).toEqual([
    { start: Date.parse(start), end: Date.parse(end) },
    { start: Date.parse('2026-10-12T01:15:00Z'), end: Date.parse('2026-10-12T01:45:00Z') },
  ]);
});

it('keeps GPU models separate and puts exact low-activity intervals behind the graph', () => {
  const period = { start, end };
  const html = renderToStaticMarkup(
    <BasicReport
      topics={[
        {
          topic_id: 'O08',
          metrics: [
            { id: 'O08.hourly_gpu_activity.0', value: 0, unit: 'percent', target, period },
            {
              id: 'O08.observed_low_activity_seconds.0',
              value: 3600,
              unit: 'seconds',
              target: { ...target, gpu_uuid: 'gpu-a100' },
              period,
            },
            {
              id: 'O08.observed_low_activity_seconds.1',
              value: 3600,
              unit: 'seconds',
              target: { ...target, model: 'H100', gpu_uuid: 'gpu-h100' },
              period,
            },
          ],
        },
      ]}
    />,
  );
  expect(html).toContain('시간대별 활동률과 저활동 구간');
  expect(html).toContain('GPU별 저활동 구간 1건');
  expect(html).toContain('<details><summary>저활동 대상·정확한 시간 확인 · 1개 구간');
  expect(html).toContain('gpu-a100');
  expect(html).not.toContain('gpu-h100');
  expect(html).toContain('Namespace 전체의 저활동을 뜻하지 않습니다');
});

it('shows missing activity and collection evidence without inventing healthy status', () => {
  const html = renderToStaticMarkup(
    <BasicReport
      topics={[
        { topic_id: 'O08', metrics: [] },
        { topic_id: 'O11', metrics: [] },
        { topic_id: 'O05', findings: [] },
      ]}
    />,
  );
  expect(html).toContain('시간별 분석을 만들지 못했습니다');
  expect(html).toContain('자료가 없어 판단할 수 없습니다');
  expect(html).toContain('기록 부재를 장애 없음으로 해석하지 않습니다');
});

it('uses a priority finding for the initial graph and orders equipment by check priority', () => {
  const period = { start, end };
  const html = renderToStaticMarkup(
    <BasicReport
      topics={[
        {
          topic_id: 'O08',
          metrics: [
            {
              id: 'O08.hourly_gpu_activity.0',
              value: 70,
              target: { ...target, namespace: 'inference' },
              period,
            },
            { id: 'O08.hourly_gpu_activity.1', value: 10, target, period },
          ],
          findings: [
            {
              id: 'O08.check.0',
              category: 'low_activity',
              priority: 2,
              text: 'training 낮은 활동',
              next_check: '작업 확인',
              target,
            },
          ],
        },
        {
          topic_id: 'O01',
          metrics: [
            {
              id: 'O01.recorded_temperature.0',
              value: 40,
              target: { node: 'record-node' },
              period,
            },
            {
              id: 'O01.node_condition_seconds.0',
              value: 30,
              target: { node: 'attention-node', condition: 'Ready', status: 'false' },
              period,
            },
          ],
          findings: [
            {
              id: 'O01.check.1',
              priority: 5,
              text: '기록 주의',
              next_check: '시각 확인',
              value_refs: ['O01.recorded_temperature.0'],
            },
            {
              id: 'O01.check.0',
              priority: 2,
              text: '상태 점검',
              next_check: 'Node 확인',
              value_refs: ['O01.node_condition_seconds.0'],
            },
          ],
        },
        {
          topic_id: 'O05',
          findings: [
            {
              id: 'O05.check.0',
              text: '사건 확인',
              next_check: '조치 확인',
              incident_id: 'i',
              action_record_ids: ['action'],
              alarm_status: 'firing',
            },
          ],
        },
      ]}
    />,
  );
  expect(html).toContain('<option selected="">test · training · A100</option>');
  const equipment = html.split('id="report-area-O01"')[1];
  expect(equipment.indexOf('attention-node')).toBeLessThan(equipment.indexOf('record-node'));
  expect(html).toContain('연결된 조치 기록 1건 · 수행 내용 확인 필요');
});

it('matches Python priority/id ordering for tied findings', () => {
  expect(
    operationalFindings([
      {
        topic_id: 'O08',
        findings: ['O08.check.2', 'O08.check.10'].map((id) => ({
          id,
          priority: 2,
          text: id,
          next_check: '확인',
        })),
      },
      {
        topic_id: 'O01',
        findings: [{ id: 'O01.check.0', priority: 2, text: 'Node', next_check: '확인' }],
      },
    ]).map((finding) => finding.id),
  ).toEqual(['O01.check.0', 'O08.check.10', 'O08.check.2']);
});
