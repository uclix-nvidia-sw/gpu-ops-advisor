import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { RcaModelFailure } from './RcaEvaluationTrace';
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
