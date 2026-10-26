import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaOperatorReport } from './RcaOperatorReport';

it('leads with saved facts, candidate, limits and the next check without changing the result', () => {
  const result = {
    result_status: 'partial',
    missing_inputs: ['causal_confirmation_evidence'],
    narrative: [
      { id: 'problem', text: '노드에서 오류가 보고되었습니다.' },
      { id: 'cause', text: '장치와 호스트 연결을 대조해야 합니다.' },
      { id: 'limits', text: '작업 영향은 확인하지 못했습니다.' },
      { id: 'next', text: '같은 시각의 작업 이력을 확인하세요.' },
    ],
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  for (const heading of ['확인한 사실', '원인 후보', '확인하지 못한 사항', '다음 확인'])
    expect(html.indexOf(heading)).toBeLessThan(html.indexOf('4. 분석 및 해석'));
  for (const section of result.narrative)
    expect(html.indexOf(section.text)).toBeLessThan(html.indexOf('4. 분석 및 해석'));
  expect(html).toContain('후보는 확정 원인이 아닙니다.');
  expect(html).toContain('보고된 증상만으로 실제 원인을 확정할 수 없습니다');
  expect(html).toContain('<section id="rca-response-reference"');
  expect(JSON.stringify(result)).toBe(before);
});

it('preserves additional limits and shows absent findings without a healthy assessment', () => {
  const html = renderToStaticMarkup(
    <RcaOperatorReport
      result={{ limitations: ['제한 1', '제한 2', '제한 3', '제한 4'] }}
      decisionSummary
    />,
  );
  expect(html).toContain('저장된 관측 사실을 확인할 수 없습니다');
  expect(html).toContain('저장된 원인 후보가 없습니다');
  expect(html).toContain('나머지 제한 1건');
  expect(html).toContain('제한 4');
  expect(html).not.toContain('정상 관측');
});

it('keeps every saved fact and next-check paragraph accessible after the two-item preview', () => {
  const facts = [
    '첫 번째 관측 원문',
    '두 번째 관측 원문',
    '세 번째 관측 원문',
    '네 번째 관측 원문',
  ];
  const checks = ['첫 번째 확인 원문', '두 번째 확인 원문', '세 번째 확인 원문'];
  const result = {
    narrative: [
      { id: 'problem', text: facts.join('\n\n') },
      { id: 'next', text: checks.join('\n\n') },
    ],
  };
  const original = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  const summary = html.slice(0, html.indexOf('id="rca-analysis-detail"'));
  expect(summary).toContain('<details><summary>나머지 관측 사실 2건</summary>');
  expect(summary).toContain('<details><summary>나머지 확인 제안 1건</summary>');
  for (const text of [...facts, ...checks]) expect(summary).toContain(text);
  expect(summary).toContain('href="#rca-response-reference"');
  expect(html).toContain('<section id="rca-response-reference"');
  expect(JSON.stringify(result)).toBe(original);
});

it('preserves the existing six-section report when the console summary is not requested', () => {
  const html = renderToStaticMarkup(<RcaOperatorReport result={{}} />);
  expect(html).not.toContain('aria-label="사건 판단 요약"');
  for (const heading of [
    '1. 한눈에 보기',
    '2. 대응 순서',
    '3. 관련 로그·메트릭',
    '4. 분석 및 해석',
    '5. 이전 사건 이력',
  ])
    expect(html).toContain(heading);
});

it('names the component reason, target, Fleet event time and live alert state', () => {
  const report = (at: string, health: string, reason: string) => ({
    component: 'disk',
    raw_health: health,
    reason,
    observed_at: at,
    target: { node: 'dgx02' },
    evidence_refs: ['log'],
  });
  const ro = 'filesystem remounted as read-only due to errors';
  const disk = JSON.parse(
    readFileSync(
      new URL('../../../rcca-agent/runbooks/component/RB-COMPONENT-DISK.json', import.meta.url),
      'utf8',
    ),
  ).content;
  const window = (value: number, at: string) => ({
    min: value,
    max: value + 5582848,
    last_value: value,
    samples: 2,
    first: at,
    last: at,
  });
  const html = renderToStaticMarkup(
    <RcaOperatorReport
      alarm={{ alarm_status: 'firing' }}
      result={{
        runbook_revisions: [{ knowledge_key: 'RB-COMPONENT-DISK', revision: 3 }],
        time_range: { start: '2026-10-26T01:36:50Z', end: '2026-10-26T02:07:48Z' },
        incident_time: '2026-10-26T02:06:50Z',
        device_observations: [
          report('2026-10-26T02:05:25Z', 'Healthy', 'ok'),
          report('2026-10-26T02:06:25Z', 'Unhealthy', ro),
        ],
        quality: {
          runbook_guidance: [
            {
              report_applicability: 'matched',
              guidance: disk.operator_guidance,
              sources: disk.sources,
            },
          ],
          component_observations: {
            schema: 'rca-component-observations/1',
            event_boundary: '2026-10-26T02:06:25Z',
            events: [
              {
                recorded_at: '2026-10-26T02:04:58Z',
                event_name: 'filesystem_read_only',
                message: `[Warning] disk: ${ro}`,
              },
            ],
            metrics: [
              {
                query_id: 'D59',
                name: '디스크 사용량 (/)',
                mount_point: '/',
                unit: 'bytes',
                kind: 'gauge',
                last: '2026-10-26T02:02:25Z',
                max_sample_gap_seconds: 480,
                incident_windows: {
                  before: window(1353207746560, '2026-10-26T02:02:25Z'),
                  at_or_after: null,
                },
              },
            ],
          },
        },
      }}
    />,
  );
  const text = html.replace(/<[^>]+>/g, '');
  expect(text).toContain('지금 알림 발생 중');
  expect(text).toContain('조회 종료 시점에도 보고 중');
  expect(text).toContain('이번 사유: 읽기 전용 재마운트 (Fleet 원문:');
  expect(text).toContain('가능한 사유 8가지: 읽기 전용 재마운트(이번) · RAID 배열 실패');
  expect(text).toContain('대상 디스크·파티션 이름은 Fleet 보고에 없습니다');
  expect(text).toContain('Fleet 커널 이벤트 기록');
  expect(text).toContain('▶ 읽기 전용 재마운트:');
  expect(text).not.toContain('▶ RAID 배열 실패:');
  expect(text).not.toContain('분기(오류 영역·사유)');
  // Byte ranges read in scaled units, never raw byte counts.
  expect(text).not.toContain('1353207746560');
});
