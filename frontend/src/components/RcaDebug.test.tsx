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
  RcaQualityGuidance,
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
      expect(html.indexOf('id="final-report"')).toBeLessThan(
        html.indexOf('<h3>확정하지 못한 이유</h3>'),
      );
      expect(html.indexOf('id="final-report"')).toBeLessThan(
        html.indexOf('분석 요약·LLM 실행 기록'),
      );
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
              'normalized_health',
              'unknown_value',
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
      '원인 확정을 위한 추가 검토',
      '장치 신원·사건 시각 연결 미확인',
      '상태·값의 의미 검증 필요',
      'LLM 분석·응답 검증 문제',
      'GPU UUID',
      'R01 알려진 오류',
      '생산자 계약·오류 코드 확인 필요',
      '로그의 상태 보고를 실제 장치의 현재 상태로 검증하지 못했습니다.',
      '수집된 값을 검증 가능한 의미로 해석하지 못했다는 포괄적 사유입니다.',
    ])
      expect(visible).toContain(text);
    expect(render(<RcaReason value="non_korean_claim" />)).toContain('한국어 문장 기준');
  });
  it('explains published and builtin selection without rewriting historical narrative', () => {
    for (const origins of [[], ['builtin'], ['published'], ['published', 'builtin']]) {
      const html = render(
        <RcaResult
          showEvidence={false}
          onEvidence={() => {}}
          job={{
            result_ref: 'published',
            result: {
              narrative: [{ id: 'limits', title: '분석 한계', text: '과거 저장 문장' }],
              runbook_revisions: origins.map((origin) => ({ origin })),
            },
          }}
        />,
      ).split('<summary>공개 결과 원본')[0];
      expect(html).toContain('과거 저장 문장');
      expect(html.includes('발행 Runbook 선택 기록이 있습니다.')).toBe(
        origins.includes('published'),
      );
      expect(html.includes('기본 일반 조사 템플릿도 추가 사용했습니다.')).toBe(
        origins.includes('published') && origins.includes('builtin'),
      );
    }
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
    ).toContain('분석 한계 원문');
    const html = render(
      <EvidenceRows
        items={[{ id: 'e', query_id: 'D05', tool_status: 'ok' }]}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('GPU 오류·상태');
  });
});

describe('RCA quality guidance', () => {
  it('separates semantics, model and causal gaps without inventing query failures', () => {
    const html = render(
      <RcaQualityGuidance
        result={{
          termination_reason: 'missing_data',
          missing_inputs: [
            'normalized_health',
            'unknown_value',
            'synthesis_failed',
            'causal_confirmation_evidence',
            'future_reason',
            'normalized_health',
          ],
        }}
      />,
    );
    for (const text of [
      '4개 범주',
      '상태·값의 의미 검증 필요 · 2개',
      'LLM 분석·응답 검증 문제',
      '원인 확정을 위한 추가 검토',
      'future_reason',
      '미수행 자체는 분석 실패가 아닙니다',
    ])
      expect(html).toContain(text);
    expect(html).not.toContain('<h4>원본 조회·수집 문제');
  });
  it('separates collection, identity and runbook gaps', () => {
    const html = render(
      <RcaQualityGuidance
        result={{
          missing_inputs: ['query_failed', 'mapping_target_unverified', 'approved_runbook'],
        }}
      />,
    );
    for (const text of [
      '원본 조회·수집 문제',
      '장치 신원·사건 시각 연결 미확인',
      '조사 절차·Runbook 확인 필요',
    ])
      expect(html).toContain(text);
  });
  it('preserves unknown legacy fields and does not infer the repair blocker', () => {
    const html = render(
      <RcaQualityGuidance
        result={{
          quality: { analysis: { synthesis: { repair_status: 'budget_or_deadline_exhausted' } } },
        }}
      />,
    );
    expect(html).toContain('미충족 조건 목록이 없습니다');
    expect(html).toContain('구 기록은 구체적 원인을 구분하지 않음');
    expect(html).not.toContain('남은 모델 예산</dt>');
    expect(render(<RcaQualityGuidance result={{ missing_inputs: [] }} />)).toContain(
      '보고된 부족 항목이 없습니다',
    );
  });
  it.each(['budget_exhausted', 'deadline_exhausted', 'budget_and_deadline_exhausted', 'repaired'])(
    'renders stored repair state %s',
    (repair_status) => {
      const html = render(
        <RcaQualityGuidance
          result={{
            quality: {
              analysis: {
                synthesis: {
                  repair_status,
                  repair_gate: { remaining_budget: 6500, remaining_seconds: null },
                },
              },
            },
          }}
        />,
      );
      expect(html).toContain(repair_status);
      expect(html).toContain('6500');
      expect(html).not.toContain('기한까지 남은 초');
    },
  );
  it('does not render unpublished guidance', () => {
    expect(
      render(
        <RcaResult
          showEvidence={false}
          onEvidence={() => {}}
          job={{ status: 'running', result: { missing_inputs: ['synthesis_failed'] } }}
        />,
      ),
    ).not.toContain('aria-label="판단 제한과 다음 확인"');
  });
});

it('keeps actionable next checks visible once and collapses repeated limitations', () => {
  const html = render(
    <RcaQualityGuidance
      result={{
        narrative: [
          { id: 'next', text: '장치 연결을 확인하세요.\n\n장치 연결을 확인하세요.' },
          { id: 'limits', text: '현재 상태는 미확정입니다.' },
        ],
        limitations: ['현재 상태는 미확정입니다.'],
      }}
    />,
  );
  expect(html.split('장치 연결을 확인하세요.')).toHaveLength(2);
  expect(html.split('현재 상태는 미확정입니다.')).toHaveLength(2);
  expect(html.indexOf('장치 연결을 확인하세요.')).toBeLessThan(html.indexOf('<details>'));
});

it('distinguishes a rejected hypothesis from a rejected limitation', () => {
  const html = render(
    <RcaQualityGuidance
      result={{
        quality: {
          analysis: {
            synthesis: {
              repair_status: 'failed',
              validation_failures: [
                {
                  attempt: 2,
                  violations: [
                    { rule: 'non_korean', hypothesis_index: 0 },
                    { rule: 'numeric', limitation_index: 1 },
                  ],
                },
              ],
            },
          },
        },
      }}
    />,
  );
  expect(html).toContain('원인 후보 문장이 한국어 설명 기준');
  expect(html).toContain('(원인 후보 1)');
  expect(html).toContain('(한계 문장 2)');
});

it('shows the recorded collection stop and outstanding queries without inferring older results', () => {
  const html = render(
    <RcaResult
      onEvidence={() => {}}
      showEvidence={false}
      job={{
        status: 'succeeded',
        result_ref: 'saved',
        result: {
          quality: {
            analysis: {
              collection_stop_reason: 'round_limit_reached',
              remaining_queries: ['D02'],
            },
          },
        },
      }}
    />,
  );
  expect(html).toContain('수집 회차 상한 도달');
  expect(html).toContain('실행하지 않은 조회 후보');
  expect(html).toContain('D02');
});

it('puts observation and collection evidence ahead of collapsed quality diagnostics', () => {
  const html = render(
    <RcaResult
      job={{
        status: 'succeeded',
        result_ref: 'published',
        result: {
          device_observations: [{ fact_eligible: false }],
          missing_inputs: ['unknown_value'],
          narrative: [
            { id: 'guidance', text: '대상 장치 확인' },
            { id: 'next', text: '중복 다음 확인 문장' },
          ],
        },
      }}
      onEvidence={() => {}}
    />,
  );
  expect(html.indexOf('관측 근거: 확인한 사실과 판단 제한')).toBeLessThan(
    html.indexOf('판단 제한·검증 진단 상세'),
  );
  expect(html).not.toContain('중복 다음 확인 문장</li>');
  expect(html).toContain('unknown_value');
});

it('explains published missing data from actual gaps and exposes subset repair', () => {
  const html = render(
    <RcaResult
      job={{
        status: 'succeeded',
        result_ref: 'published',
        result: {
          termination_reason: 'missing_data',
          missing_inputs: ['causal_confirmation_evidence'],
          quality: {
            analysis: {
              status: 'complete',
              synthesis: { repair_status: 'failed', completion_mode: 'validated_subset' },
            },
          },
        },
      }}
      onEvidence={() => {}}
    />,
  );
  expect(html).toContain('보고된 증상만으로 실제 원인을 확정할 수 없습니다');
  expect(html).not.toContain('필수 근거가 부족합니다. 부족 항목을 확인하세요');
  expect(html).toContain('응답 일부만 사용했습니다');
});
it('does not describe rejected analysis as a usable subset', () => {
  const html = render(
    <RcaResult
      job={{
        status: 'succeeded',
        result_ref: 'published',
        result: {
          quality: { analysis: { status: 'failed', synthesis: { repair_status: 'failed' } } },
        },
      }}
      onEvidence={() => {}}
    />,
  );
  expect(html).toContain('LLM 분석 응답 미채택');
  expect(html).not.toContain('응답 일부만 사용했습니다');
});
