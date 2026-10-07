import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  EvidenceRows,
  IncidentDebug,
  IncidentStates,
  RcaJobSummary,
  RcaReason,
  RcaResult,
} from './RcaDebug';
import { AlarmIdentity, DataView, JobRows } from './live';

const render = (node: ReactNode) =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
describe('RCA diagnostics', () => {
  it('separates synthesis preflight failure from report LLM calls and handles legacy results', () => {
    const job = {
      id: 'job',
      result_ref: 'result',
      result: {
        llm_usage: { calls: 1 },
        quality: {
          analysis: {
            status: 'failed',
            synthesis: {
              request_attempts: 0,
              response_calls: 0,
              error_code: 'llm_context_budget_exhausted',
            },
          },
        },
      },
    };
    const html = render(<RcaResult job={job} onEvidence={() => {}} />);
    expect(html).toContain('RCA 분석 요청 시도</dt><dd>0건');
    expect(html).toContain('LLM 응답 사용 기록</dt><dd>1건');
    expect(html).toContain('분석 요청을 생략했습니다');
    expect(html).toContain('최종 보고서 편집도 포함');
    expect(
      render(<RcaResult job={{ result_ref: 'old', result: {} }} onEvidence={() => {}} />),
    ).toContain('구 결과에는 단계별 기록이 없습니다');
  });
  it('labels every missing input the RCA worker emits for this incident', () => {
    for (const code of [
      'error_code',
      'observation_degraded',
      'synthesis_failed',
      'approved_runbook',
    ]) {
      expect(render(<RcaReason value={code} />)).not.toContain('사유 코드 <code>');
    }
  });
  it('explains synthesis validation failure codes instead of a bare code', () => {
    const job = {
      id: 'job',
      result_ref: 'result',
      result: {
        llm_usage: { calls: 2 },
        quality: {
          analysis: {
            status: 'failed',
            synthesis: {
              request_attempts: 1,
              response_calls: 1,
              error_code: 'invalid_limitations',
            },
          },
        },
      },
    };
    const html = render(<RcaResult job={job} onEvidence={() => {}} />);
    expect(html).toContain('RCA 분석 요청 시도</dt><dd>1건');
    expect(html).toContain(
      '분석 한계 문장이 형식·한국어·숫자 또는 입력 근거 제한을 통과하지 못했습니다',
    );
    expect(html).not.toContain('사유 코드 <code>invalid_limitations');
  });
  it('links only published RCA and Ops reports directly from lists', () => {
    const html = render(
      <JobRows
        items={[
          { id: 'rca-ready', kind: 'rca', result_ref: 'r1' },
          { id: 'ops-ready', kind: 'report', result_ref: 'r2' },
          { id: 'pending', kind: 'rca', status: 'succeeded' },
        ]}
      />,
    );
    expect(html).toContain('/analyses/rca-ready#final-report');
    expect(html).toContain('href="/jobs/rca-ready"');
    expect(html).toContain('href="/jobs/ops-ready"');
    expect(html).toMatch(
      /href="\/analyses\/rca-ready#final-report"[^>]*><span class="alarm-identity"/,
    );
    expect(html).toContain('/reports/ops-ready#final-report');
    expect(html).not.toContain('/analyses/pending#final-report');
    expect(html).toContain('미발행');
  });
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

describe('Korean RCA report labels', () => {
  it('renders runbook investigation questions without a purpose code', () => {
    const html = render(
      <RcaResult
        showEvidence={false}
        onEvidence={() => {}}
        job={{
          result_ref: 'published',
          result: {
            assessments: [
              {
                assessment_id: 'book-1',
                question: '온도 이상 조사',
                status: 'partial',
                missing_inputs: ['observations'],
              },
            ],
          },
        }}
      />,
    );
    expect(html).toContain('조사별 판단');
    expect(html).toContain('<h4>온도 이상 조사</h4>');
    expect(html).not.toContain('R01');
  });
  it('groups missing evidence and renders limitations once outside raw details', () => {
    const html = render(
      <RcaResult
        showEvidence={false}
        onEvidence={() => {}}
        job={{
          result_ref: 'published',
          result: {
            missing_inputs: [
              'causal_confirmation_evidence',
              'incident_mapping',
              'producer_contract',
              'synthesis_failed',
            ],
            limitations: ['고유한 분석 한계 문장'],
            narrative: [{ id: 'limits', title: '분석 한계', text: '고유한 분석 한계 문장' }],
            assessments: [{ purpose_id: 'R01', status: 'blocked' }],
          },
        }}
      />,
    );
    const visible = html.split('<summary>공개 결과 원본')[0];
    expect(visible.match(/고유한 분석 한계 문장/g)).toHaveLength(1);
    for (const text of [
      '설계상 항상 남음',
      '데이터 원천 부재',
      '생산자 계약 미확인',
      '이번 실행의 수집·분석 품질',
      'gpu_ops_allocation_info',
      'R01 알려진 오류',
      '생산자 계약·오류 코드 확인 필요',
    ])
      expect(visible).toContain(text);
    expect(render(<RcaReason value="non_korean_claim" />)).toContain('한국어 문장 기준');
  });
  it('keeps legacy limitations and explains query names', () => {
    expect(
      render(
        <RcaResult
          showEvidence={false}
          onEvidence={() => {}}
          job={{ result_ref: 'old', result: { limitations: ['과거 한계'] } }}
        />,
      ),
    ).toContain('<h3>분석 한계</h3>');
    const html = render(
      <EvidenceRows
        items={[{ id: 'e', query_id: 'D05', tool_status: 'ok' }]}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('GPU 오류·상태');
  });
});
