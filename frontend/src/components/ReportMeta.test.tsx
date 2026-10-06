import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReportExecution, ReportOrigin, ReportScope } from './ReportMeta';
import { DataView } from './live';

it('distinguishes scheduled, manual and unknown origins without guessing', () => {
  for (const [value, label] of [
    ['schedule', '자동 생성'],
    ['manual', '직접 요청'],
    [undefined, '생성 방식 미확인'],
    ['legacy', '생성 방식 미확인'],
  ]) {
    expect(renderToStaticMarkup(<ReportOrigin value={value} />)).toContain(`생성 방식: ${label}`);
  }
});
it('renders report timestamps in Korea time across a day boundary without changing durations or raw values', () => {
  const value = {
    period: { start: '2026-09-30T15:00:00Z', end: '2026-10-01T16:00:00+01:00' },
    timezone: 'UTC',
    duration_seconds: 86400,
  };
  const html = renderToStaticMarkup(<DataView value={value} reportDisplay />);
  expect(html).toContain('10. 01.');
  expect(html).toContain('10. 02.');
  expect(html).not.toContain('T15:00:00Z');
  expect(html).not.toContain('UTC');
  expect(html).toContain('86400');
  expect(renderToStaticMarkup(<DataView value={value} />)).toContain('2026-09-30T15:00:00Z');
  expect(value.period.start).toBe('2026-09-30T15:00:00Z');
});

it('separates clusters from Namespace scope and preserves all, selected, empty and unknown scopes', () => {
  const html = renderToStaticMarkup(
    <ReportScope
      job={{
        scope: {
          clusters: [
            { cluster_id: 'cpc-1', namespaces: null },
            { cluster_id: 'cpc-2', namespaces: ['training', 'inference'] },
            { cluster_id: 'cpc-3', namespaces: [] },
            { cluster_id: 'cpc-4' },
          ],
        },
      }}
    />,
  );
  expect(html.match(/<li>/g)).toHaveLength(4);
  const blocks = html.split('<li>').slice(1);
  for (const [index, scope] of [
    '전체 Namespace',
    'training, inference',
    '선택된 Namespace 없음',
    'Namespace 범위 미확인',
  ].entries()) {
    expect(blocks[index]).toContain(`cpc-${index + 1}`);
    expect(blocks[index]).toContain('Namespace 범위');
    expect(blocks[index]).toContain(scope);
  }
  expect(renderToStaticMarkup(<ReportScope job={{}} />)).toContain('분석 대상 미확인');
});

const executionJob = {
  status: 'succeeded',
  attempt_no: 1,
  created_at: '2026-10-02T00:00:00Z',
  attempts: [
    { attempt_no: 1, started_at: '2026-10-02T00:01:00Z', ended_at: '2026-10-02T00:05:49.783Z' },
  ],
};
it('separates report execution from queue time using saved attempt timestamps', () => {
  const html = renderToStaticMarkup(<ReportExecution job={executionJob} />);
  expect(html).toContain('<strong>4분 50초</strong>');
  expect(html).toContain('대기 제외');
  expect(html).toContain('접수부터 완료까지 5분 50초 · 대기 포함');
});
it('adds every retry execution while excluding retry waits and preserving input order', () => {
  const job = {
    ...executionJob,
    attempt_no: 2,
    attempts: [
      {
        attempt_no: 2,
        started_at: '2026-10-02T09:13:00+09:00',
        ended_at: '2026-10-02T09:16:00+09:00',
      },
      { attempt_no: 1, started_at: '2026-10-02T00:01:00Z', ended_at: '2026-10-02T00:03:00Z' },
    ],
  };
  const before = JSON.stringify(job);
  const html = renderToStaticMarkup(<ReportExecution job={job} />);
  expect(html).toContain('<strong>5분 0초</strong>');
  expect(html).toContain('2회 시도 합계');
  expect(html).toContain('접수부터 완료까지 16분 0초');
  expect(JSON.stringify(job)).toBe(before);
});
it.each([
  ['queued', '아직 실행 전'],
  ['running', '실행 중 · 완료 후 표시'],
  ['retry_wait', '재시도 대기 · 완료 후 표시'],
  ['failed', '보고서 생성 실패'],
  ['cancelled', '보고서 생성 취소'],
  ['expired', '보고서 생성 기한 만료'],
])('does not show a completed duration for %s', (status, text) => {
  const html = renderToStaticMarkup(<ReportExecution job={{ ...executionJob, status }} />);
  expect(html).toContain(text);
  expect(html).not.toContain('접수부터 완료까지');
});
it('keeps missing, reversed, duplicate, overlapping and incomplete execution records unknown', () => {
  for (const patch of [
    { attempts: undefined },
    { attempt_no: 2 },
    { attempts: [{ ...executionJob.attempts[0], ended_at: null }] },
    { attempts: [{ ...executionJob.attempts[0], ended_at: 'invalid' }] },
    { attempts: [{ ...executionJob.attempts[0], ended_at: '2026-10-01T00:00:00Z' }] },
    { attempt_no: 2, attempts: [executionJob.attempts[0], executionJob.attempts[0]] },
    {
      attempt_no: 2,
      attempts: [executionJob.attempts[0], { ...executionJob.attempts[0], attempt_no: 2 }],
    },
  ]) {
    expect(renderToStaticMarkup(<ReportExecution job={{ ...executionJob, ...patch }} />)).toContain(
      '실행시간 미확인',
    );
  }
  const html = renderToStaticMarkup(
    <ReportExecution job={{ ...executionJob, created_at: null }} />,
  );
  expect(html).toContain('<strong>4분 50초</strong>');
  expect(html).toContain('접수부터 완료까지 미확인');
});
