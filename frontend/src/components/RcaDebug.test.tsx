import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { EvidenceRows, IncidentDebug, IncidentStates, RcaJobSummary, RcaResult } from './RcaDebug';
import { AlarmIdentity, DataView, JobRows } from './live';

const render = (node: ReactNode) =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
describe('RCA diagnostics', () => {
  it('shows stored alarm names and targets with job IDs, without inventing absent names', () => {
    const job = {
      id: 'job-123',
      kind: 'rca',
      target: { alertname: 'GPUHighTemperature', node: 'gpu-node-1', cluster_id: 'cpc-2' },
    };
    const html = render(<JobRows items={[job]} />);
    expect(html).toContain('GPUHighTemperature');
    expect(html).toContain('노드: gpu-node-1');
    expect(html).toContain('작업 ID · job-123');
    expect(render(<AlarmIdentity record={{}} />)).toContain('알람 이름 미확인');
    expect(
      render(<AlarmIdentity record={{ target: { alertname: '<script>bad</script>' } }} />),
    ).not.toContain('<script>');
  });
  it('explains raw fields using keyboard-accessible disclosure and separates alarm resolution', () => {
    const html = render(
      <DataView
        value={{ alarm_status: 'resolved', observation_count: 0, asset_key: null }}
        explain
      />,
    );
    expect(html).toContain('<summary');
    expect(html).toContain('알람 상태');
    expect(html).toContain('사건 종결과는 별개');
    expect(html).toContain('<code>alarm_status</code>');
    expect(html).toContain('해제됨');
    expect(html).not.toContain('해결됨');
    expect(html).toContain('>0</span>');
    expect(html).toContain('미확인');
  });
  it('keeps resolved alarms separate from open incidents and human review', () => {
    const html = render(
      <IncidentStates
        incident={{
          alarm_status: 'resolved',
          state: 'open',
          status: 'critical',
          review_status: 'reviewing',
        }}
      />,
    );
    expect(html).toContain('해제됨');
    expect(html).toContain('열림');
    expect(html).toContain('검토 중');
    expect(html).not.toContain('해결됨');
    expect(html).not.toContain('긴급');
  });
  it('links each job from the incident and explains absent jobs', () => {
    expect(
      render(<IncidentDebug incident={{ analyses: [{ job_id: 'job-a', status: 'running' }] }} />),
    ).toContain('href="/jobs/job-a"');
    const empty = render(<IncidentDebug incident={{ rca_eligibility_reason: 'stale_alert' }} />);
    expect(empty).toContain('연결된 RCA 작업이 없습니다');
    expect(empty).toContain('stale_alert');
  });
  it('does not invent a publication or a completed collection while running', () => {
    const html = render(
      <RcaJobSummary
        job={{ status: 'running', stage: 'workflow', attempt_no: 2, incident_id: 'incident-a' }}
      />,
    );
    expect(html).toContain('아직 공개된 결과가 없습니다');
    expect(html).toContain('워크플로우 종료 후 일괄 저장');
    expect(html).toContain('href="/incidents/incident-a"');
    expect(html).not.toContain('결과 공개 완료');
  });
  it('shows succeeded + blocked + zero LLM records without claiming connection failure', () => {
    const html = render(
      <RcaResult
        job={{
          id: 'job-a',
          status: 'succeeded',
          result_ref: 'candidate-a',
          result: {
            result_status: 'blocked',
            termination_reason: 'query_failed',
            llm_usage: { calls: 0 },
            quality: { analysis: { status: 'no_usable_evidence' } },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('결과 공개 완료');
    expect(html).toContain('근거 부족');
    expect(html).toContain('관측 조회가 실패');
    expect(html).toContain('연결 실패를 판단하지 않습니다');
    expect(html).toContain('공개 결과에 근거 참조가 없습니다');
  });
  it('hides unpublished result bodies', () => {
    const html = render(
      <RcaResult
        job={{ status: 'failed', result: { summary: 'candidate-must-stay-hidden' } }}
        onEvidence={() => {}}
      />,
    );
    expect(html).not.toContain('candidate-must-stay-hidden');
    expect(html).toContain('공개 결과 없음');
  });
  it.each(['complete', 'failed', 'omitted'])(
    'renders the final report with narrative status %s',
    (status) => {
      const html = render(
        <RcaResult
          job={{
            status: 'succeeded',
            result_ref: 'published',
            result: {
              result_status: 'blocked',
              narrative_status: status,
              narrative: [
                {
                  id: 'problem',
                  title: '감지된 문제',
                  text: 'XID 79 <script>bad</script>\n\n원인 미확정',
                },
                { id: 'action', title: '권고 조치와 조건', text: '실행 보류·미수행' },
              ],
            },
          }}
          onEvidence={() => {}}
        />,
      );
      expect(html).toContain('RCA 최종 보고서');
      expect(html).toContain('권고 조치와 조건');
      expect(html).toContain('원인 미확정');
      expect(html).toContain('실행 보류·미수행');
      expect(html).not.toContain('<script>');
      expect(html).toContain(status === 'complete' ? 'LLM이 우선순위' : '기본 보고서');
    },
  );
  it('prioritizes failed collection and preserves empty, partial, zero and unknown', () => {
    const items = [
      {
        id: 'ok',
        query_id: 'D01',
        tool_status: 'ok',
        quality: { complete: true, sample_count: 4 },
      },
      {
        id: 'empty',
        query_id: 'D02',
        tool_status: 'empty',
        quality: { complete: true, sample_count: 0 },
      },
      { id: 'partial', query_id: 'D03', tool_status: 'partial', quality: { complete: false } },
      {
        id: 'failed',
        query_id: 'D09',
        tool_status: 'unavailable',
        quality: { error_code: 'loki_entry_limit_exceeded' },
      },
    ];
    const html = render(<EvidenceRows items={items} onEvidence={() => {}} />);
    expect(html.indexOf('D09')).toBeLessThan(html.indexOf('D03'));
    expect(html.indexOf('D03')).toBeLessThan(html.indexOf('D02'));
    for (const text of [
      '빈 결과',
      '부분 수집',
      '완전성: 미확인',
      '응답 표본: 0',
      '응답 표본: 미확인',
      'loki_entry_limit_exceeded',
    ])
      expect(html).toContain(text);
    expect(items[0].id).toBe('ok');
  });
});
