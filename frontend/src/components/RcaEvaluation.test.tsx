import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaEvaluation } from './RcaEvaluation';
import { RcaEvaluationTrace, RcaStageDetails } from './RcaEvaluationTrace';

describe('separate RCA evaluations', () => {
  const result = {
    result_status: 'partial',
    quality: {
      rca_evaluation: {
        schema_version: '1',
        analysis_id: 'final-draft',
        collection: { status: 'partial' },
        evidence: { execution_status: 'complete' },
        review: {
          execution_status: 'complete',
          verdict: 'acceptable',
          analysis_id: 'final-draft',
          rubric_version: '1',
          criteria: {
            grounding: {
              status: 'pass',
              reason: 'GPU 연결 미확인을 명시함',
              evidence_refs: ['source-log'],
            },
          },
        },
        investigation: { status: 'finished', stop_reason: 'no_available_followup' },
      },
    },
  };
  it('shows partial collection with an acceptable limited analysis without changing existing status', () => {
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaEvaluation result={result} />);
    for (const text of [
      '부분 수집',
      '근거 범위에서 타당',
      '원인 확정을 뜻하지 않습니다',
      'GPU 연결 미확인을 명시함',
      'source-log',
    ])
      expect(html).toContain(text);
    expect(JSON.stringify(result)).toBe(before);
  });
  it('never labels an old draft, failed review, missing extension or unknown version acceptable', () => {
    for (const change of [
      { analysis_id: 'old-draft' },
      { execution_status: 'failed' },
      { execution_status: 'skipped' },
    ]) {
      const value = structuredClone(result);
      Object.assign(value.quality.rca_evaluation.review, change);
      const html = renderToStaticMarkup(<RcaEvaluation result={value} />);
      expect(html).toContain('미검토');
      expect(html).not.toContain('근거 범위에서 타당');
    }
    expect(renderToStaticMarkup(<RcaEvaluation result={{}} />)).toContain('검토 기록이 없습니다');
    const value = structuredClone(result);
    value.quality.rca_evaluation.schema_version = '99';
    expect(renderToStaticMarkup(<RcaEvaluation result={value} />)).toContain(
      '지원하지 않는 평가 형식',
    );
  });
  it('distinguishes stage ownership from actual model calls and exposes the review target', () => {
    const html = renderToStaticMarkup(
      <RcaEvaluationTrace
        onEvidence={() => {}}
        items={[
          {
            id: 'review',
            query_id: 'analysis_review',
            quality: {
              round: 1,
              execution_status: 'skipped',
              reason: 'draft_changed_after_review',
              attempts: 0,
              analysis_id: 'new-draft',
            },
          },
          {
            id: 'decision',
            query_id: 'investigation_decision',
            quality: { round: 1, action: 'finish', reason: 'llm_budget_exhausted' },
          },
        ]}
      />,
    );
    for (const text of [
      '2회차',
      'LLM ③',
      '논리 모델 요청 0회',
      'new-draft',
      '최종 초안은 미검토',
      'LLM 예산 소진',
      '조회 식별자',
    ])
      expect(html).toContain(text);
  });
  it('renders interpretation, rubric reasons, source links and omissions for debugging', () => {
    const html = renderToStaticMarkup(
      <RcaStageDetails
        onEvidence={() => {}}
        record={{
          query_id: 'analysis_review',
          snapshot: {
            analysis_id: 'draft-2',
            rubric_version: '1',
            context_selection: { complete: false },
            review: {
              verdict: 'revision_required',
              criteria: {
                grounding: {
                  status: 'needs_revision',
                  reason: '공백 동안 원인을 배제할 수 없음',
                  evidence_refs: ['log-1'],
                },
              },
              issues: [
                {
                  claim_id: 'cause:c1',
                  reason: '단정',
                  suggested_resolution: '한계 명시',
                  evidence_refs: ['log-1'],
                },
              ],
              followup_questions: [
                { question: '연결 확인', expected_effect: '대상 판단 변경', query_ids: ['D44'] },
              ],
            },
          },
        }}
      />,
    );
    for (const text of [
      '평가 척도',
      '공백 동안 원인을 배제할 수 없음',
      'log-1',
      'cause:c1',
      '실제 실행 결정과 구분',
      '일부 자료가 생략',
    ])
      expect(html).toContain(text);
  });
});
