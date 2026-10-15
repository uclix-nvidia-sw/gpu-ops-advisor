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
  it('shows the combined author and independent reviewer without inventing a third stage', () => {
    const records = ['rca_synthesis', 'analysis_review'].map((query_id) => ({
      id: query_id,
      query_id,
      quality: { generation_mode: 'combined' },
      snapshot: { generation_mode: 'combined' },
    }));
    const html = renderToStaticMarkup(<RcaEvaluationTrace items={records} onEvidence={() => {}} />);
    expect(html).toContain('증거 해석·RCA 분석');
    expect(html).toContain('작성 LLM');
    expect(html).toContain('별도 검토 LLM');
    expect(html).not.toContain('LLM ③');
  });
  it('shows objective criteria and never treats a stale review as completed investigation', () => {
    const value = structuredClone(result);
    Object.assign(value.quality.rca_evaluation, {
      schema_version: '2',
      generation_mode: 'combined',
    });
    Object.assign(value.quality.rca_evaluation.investigation, {
      objective: {
        status: 'achieved',
        analysis_id: 'final-draft',
        policies: [
          {
            runbook_revision_id: 'book-1',
            content_hash: 'hash',
            goal: {
              question: '대상 노드의 오류 보고를 확인했는가?',
              conclusion_scope: '현재 상태와 근본 원인은 미확정',
            },
            criteria: [
              {
                key: 'criterion-1',
                question: '보고 내용의 한계를 설명했는가?',
                required: true,
                method: 'llm',
                status: 'satisfied',
                evidence_refs: ['original-log'],
              },
            ],
            blocking_conditions: [],
            unmet_required_evidence: [],
            non_blocking_unknowns: ['current_health'],
          },
        ],
      },
    });
    const html = renderToStaticMarkup(<RcaEvaluation result={value} />);
    for (const text of [
      '조사 목적 달성',
      '대상 노드의 오류 보고',
      '보고 내용의 한계',
      'original-log',
      '현재 장치 상태',
    ])
      expect(html).toContain(text);
    value.quality.rca_evaluation.review.analysis_id = 'old-draft';
    const stale = renderToStaticMarkup(<RcaEvaluation result={value} />);
    expect(stale).not.toContain('<h4>조사 목적 달성</h4>');
    expect(stale).toContain('미검토');
  });
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

  it.each([
    [true, false, 'llm_input_size_exceeded', '모델 입력 크기 상한 초과'],
    [false, true, 'llm_token_budget_exhausted', '남은 모델 토큰 예산 부족'],
    [true, true, 'llm_input_size_exceeded', '모델 입력 크기 상한 초과'],
  ])(
    'shows independent limits in the trace and stage details (%s, %s)',
    (size, tokens, reason, text) => {
      const diagnostic = {
        execution_status: 'skipped',
        reason,
        attempts: 0,
        request_checks: [
          {
            input_bytes: 25012,
            max_input_bytes: 24000,
            remaining_tokens: 1000000,
            reserved_tokens: 100,
            available_tokens: 999900,
            required_tokens: 26000,
            output_token_cap: 4096,
            input_size_exceeded: size,
            token_budget_exhausted: tokens,
            model_called: false,
          },
        ],
      };
      const record = {
        id: 'review-limit',
        query_id: 'analysis_review',
        quality: diagnostic,
        snapshot: diagnostic,
      };
      for (const html of [
        renderToStaticMarkup(<RcaEvaluationTrace items={[record]} onEvidence={() => {}} />),
        renderToStaticMarkup(<RcaStageDetails record={record} />),
      ]) {
        for (const expected of [
          text,
          '25,012',
          '24,000',
          '1,000,000',
          '999,900',
          '4,096',
          '실제 사용량이 아닙니다',
          '모델 호출 전 생략',
          size ? '상한 초과' : '상한 이내',
          tokens ? '토큰 예산: 부족' : '토큰 예산: 사전 검사 충족',
        ])
          expect(html).toContain(expected);
        expect(html).not.toContain('근거 범위에서 타당');
      }
      const value = structuredClone(result);
      Object.assign(value.quality.rca_evaluation.review, {
        execution_status: 'skipped',
        verdict: null,
        reason,
      });
      const html = renderToStaticMarkup(<RcaEvaluation result={value} />);
      expect(html).toContain(text);
      expect(html).toContain('미검토');
    },
  );

  it('preserves fallback failure, conservative charges and unknown legacy checks', () => {
    const body = {
      execution_status: 'skipped',
      reason: 'draft_changed_after_review',
      failure_reason: 'llm_input_size_exceeded',
      usage: {
        request_attempts: 1,
        total_tokens: 0,
        charged_tokens: 2000,
        estimated_tokens: 2000,
        usage_missing_calls: 1,
      },
    };
    const html = renderToStaticMarkup(
      <RcaStageDetails record={{ query_id: 'analysis_review', snapshot: body }} />,
    );
    for (const text of [
      '최종 초안은 미검토',
      '재검토 실패: 모델 입력 크기 상한 초과',
      '사전 검사: 기록 없음',
      '미보고 응답 1건',
      '보수적 차감 2,000토큰',
    ])
      expect(html).toContain(text);
    expect(html).not.toContain('사전 검사 충족');
  });
});
