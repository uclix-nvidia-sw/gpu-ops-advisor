import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { RcaModelFailure, stageForRecord, reviewStatus } from './RcaEvaluationTrace';
import { RcaWorkflowRecord } from './RcaWorkflow';
import { RcaJobSummary } from './RcaDebug';

describe('RCA request failure versus response validation', () => {
  it.each([
    ['invalid_author_response', '응답 수신 · 통합 분석 검증 실패'],
    ['llm_invalid_output', '응답 수신 · JSON 해석 실패'],
    ['llm_output_truncated', '응답 수신 · 출력 잘림'],
    ['llm_http_error', '모델 요청 실패 · HTTP 오류'],
    ['model_not_configured', '호출 전 생략 · 모델 미설정'],
    ['llm_token_budget_exhausted', '호출 전 생략 · 토큰 예산 부족'],
    ['llm_no_response', '유효한 응답 없음 · 원인 미확인'],
    ['future_error', '실패 유형 미분류 · 저장 사유 확인'],
  ])('explains %s without guessing the failure category', (code, title) => {
    const html = renderToStaticMarkup(<RcaModelFailure diagnostic={{ error_code: code }} />);
    expect(html).toContain(title);
    expect(html).toContain(`<code>${code}</code>`);
    expect(html).not.toContain('해석·분석 모두 미채택');
  });

  it('shows received but excluded author output in the workflow popup', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'rca_synthesis',
          snapshot: {
            generation_mode: 'combined',
            status: 'failed',
            usage: { request_attempts: 1, calls: 1 },
            diagnostics: {
              error_code: 'invalid_author_response',
              adoption: 'none',
              validation_failures: [{ attempt: 1, reasons: ['author_shape'] }],
            },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('응답 기록 1건');
    expect(html).toContain('응답 수신 · 통합 분석 검증 실패');
    expect(html).toContain('통합 응답의 최상위 구조가 다릅니다');
    expect(html).toContain('해석·분석 모두 미채택');
    expect(html).toContain('실제 누락·추가 항목은 이 기록에 저장되지 않았습니다');
    expect(html).not.toContain('모델 요청 실패 · HTTP 오류');
  });

  it('keeps partial interpretation adoption and a changed draft distinct from transport failure', () => {
    const html = renderToStaticMarkup(
      <RcaModelFailure
        diagnostic={{
          error_code: 'invalid_author_response',
          adoption: 'interpretation_only',
          validation_failures: [{ attempt: 1, reasons: ['analysis_invalid'] }],
        }}
      />,
    );
    expect(html).toContain('증거 해석만 보존 · 원인 분석 미채택');
    expect(html).not.toContain('해석·분석 모두 미채택');
    const skipped = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'analysis_review',
          snapshot: {
            execution_status: 'skipped',
            reason: 'draft_changed_after_review',
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(skipped).not.toContain('모델 호출과 응답 검증 구분');
  });

  it('shows communication uncertainty for the current attempt only', () => {
    const render = (attempt_no: number) =>
      renderToStaticMarkup(
        <MemoryRouter>
          <RcaJobSummary
            job={{
              kind: 'rca',
              status: 'failed',
              attempt_no,
              attempts: [
                { attempt_no: 1, remote_call_state: 'unknown' },
                { attempt_no: 2, remote_call_state: 'terminated' },
              ],
            }}
          />
        </MemoryRouter>,
      );
    expect(render(1)).toContain('모델 통신 중단 · 원격 실행 상태 미확인');
    expect(render(2)).not.toContain('모델 통신 중단');
  });
});

describe('precise RCA validation and review state', () => {
  it('shows the failed item and explanation before internal codes', () => {
    const html = renderToStaticMarkup(
      <RcaModelFailure
        diagnostic={{
          error_code: 'invalid_author_response',
          adoption: 'interpretation_only',
          validation_failures: [
            {
              reasons: ['analysis_invalid'],
              details: [
                {
                  code: 'invalid_evidence_references',
                  rule: 'unknown_observation_refs',
                  hypothesis_index: 1,
                  path: '$.hypotheses[1]',
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('원인 후보 2');
    expect(html).toContain('허용된 관측 근거에 없는 ID를 인용했습니다');
    expect(html).toContain('<details><summary>검증 위치·코드</summary>');
    expect(html).toContain('$.hypotheses[1]');
    expect(html).not.toContain('원인 분석의 형식·근거 참조 또는 해석과의 연결 검증에 실패했습니다');
  });

  it('does not invent details for older failures', () => {
    const html = renderToStaticMarkup(
      <RcaModelFailure
        diagnostic={{
          error_code: 'invalid_author_response',
          validation_failures: [{ reasons: ['analysis_invalid'] }],
        }}
      />,
    );
    expect(html).toContain('세부 검증 위치·사유가 저장되지 않았습니다');
    expect(html).not.toContain('원인 후보 1');
  });

  it('labels skipped review as a code record, and completed review with its verdict', () => {
    const skipped = {
      query_id: 'analysis_review',
      snapshot: {
        execution_status: 'skipped',
        reason: 'draft_changed_after_review',
        attempts: 0,
        previous_review_evidence_id: 'previous-review',
      },
    };
    const html = renderToStaticMarkup(<RcaWorkflowRecord record={skipped} onEvidence={() => {}} />);
    expect(html).toContain('변경 초안 미검토');
    expect(html).toContain('미실행 상태 기록');
    expect(html).toContain('LLM 호출 없음');
    expect(html).toContain('이전 검토 지적 확인');
    expect(html).not.toContain('기록 성격: LLM 처리');
    expect(html).not.toContain('6개 척도');
    expect(html).not.toContain('요청 크기·예산 사전 검사');
    expect(stageForRecord({ query_id: 'analysis_review', quality: skipped.snapshot })?.title).toBe(
      '변경 초안 미검토',
    );
    expect(
      reviewStatus({
        query_id: 'analysis_review',
        quality: { execution_status: 'complete', verdict: 'revision_required' },
      }),
    ).toBe('검토 완료 · 수정 필요');
    expect(
      stageForRecord({
        query_id: 'rca_analysis_draft',
        quality: { reason: 'review_claims_withheld' },
      })?.title,
    ).toBe('주장 제외 후 초안 저장');
    expect(
      stageForRecord({ query_id: 'investigation_decision', quality: { action: 'withhold' } })
        ?.title,
    ).toBe('검토 지적에 따라 주장 제외');
  });
});

it('uses an explicit same-draft skipped review to label legacy draft records', () => {
  const draft = {
    query_id: 'rca_analysis_draft',
    job_id: 'job',
    attempt_no: 1,
    quality: { analysis_id: 'same' },
  };
  const review = {
    query_id: 'analysis_review',
    job_id: 'job',
    attempt_no: 1,
    quality: {
      analysis_id: 'same',
      execution_status: 'skipped',
      reason: 'draft_changed_after_review',
      attempts: 0,
    },
  };
  expect(stageForRecord(draft, [review])?.title).toBe('검토 후 변경 초안 저장');
  expect(stageForRecord(draft, [{ ...review, attempt_no: 2 }])?.title).toBe('검토할 초안 고정');
  expect(
    stageForRecord(draft, [{ ...review, quality: { ...review.quality, analysis_id: 'other' } }])
      ?.title,
  ).toBe('검토할 초안 고정');
});

it('keeps historical calls visible when the final draft is unreviewed', () => {
  const record = {
    query_id: 'analysis_review',
    snapshot: {
      execution_status: 'skipped',
      reason: 'draft_changed_after_review',
      attempts: 0,
      failure_reason: 'llm_output_truncated',
      usage: { request_attempts: 1, calls: 1 },
    },
  };
  expect(reviewStatus(record)).toBe('미검토');
  const html = renderToStaticMarkup(<RcaWorkflowRecord record={record} onEvidence={() => {}} />);
  expect(html).toContain('모델 전송 시도 1회 · 응답 기록 1건');
  expect(html).not.toContain('미실행 상태 기록');
  expect(html).not.toContain('LLM 호출 없음');
});

it('does not show author adoption on review or draft records', () => {
  for (const query_id of ['analysis_review', 'rca_analysis_draft', 'investigation_decision']) {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{ query_id, snapshot: { generation_mode: 'combined' } }}
        onEvidence={() => {}}
      />,
    );
    expect(html).not.toContain('aria-label="통합 작성 결과"');
    expect(html).not.toContain('작성 결과를 채택하지 못했습니다');
  }
});
