import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RcaWorkflowButton, RcaWorkflowRecord } from './RcaWorkflow';

describe('developer RCA workflow entry and evidence', () => {
  it('shows the actual goal decision with collected and omitted queries in workflow details', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'investigation_decision',
          snapshot: {
            action: 'finish',
            reason: 'goal_achieved',
            decision_policy_status: 'applied',
            collected_queries: ['D09'],
            deferred_queries: ['D44', 'D02', 'D11'],
            decision_assessment: {
              status: 'achieved',
              policies: [
                {
                  runbook_revision_id: 'published-policy',
                  goal: { question: 'XID 79 보고를 식별했는가?' },
                  criteria: [],
                  blocking_conditions: [],
                  non_blocking_unknowns: ['current_health'],
                },
              ],
            },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    for (const text of [
      '조사 목적 달성',
      'XID 79 보고',
      '목표 확인에 사용한 수집: D09',
      '목표를 충족해 추가로 수집하지 않은 선택 조회: D44, D02, D11',
      '현재 장치 상태',
    ])
      expect(html).toContain(text);
  });
  it('explains combined authoring and frozen RCA material separately from report composition', () => {
    const render = (query_id: string, snapshot: Record<string, unknown>) =>
      renderToStaticMarkup(
        <RcaWorkflowRecord record={{ query_id, snapshot }} onEvidence={() => {}} />,
      );
    const author = render('rca_synthesis', { generation_mode: 'combined' });
    expect(author).toContain('증거 해석·RCA 분석');
    expect(author).toContain('작성 LLM');
    expect(author).not.toContain('LLM ②');
    const frozen = render('rca_result_frozen', { material_hash: 'material-hash' });
    expect(frozen).toContain('material-hash');
    expect(frozen).toContain('자료가 바뀌면 결과 공개를 중단');
    const report = render('report_assembly', { report: { method: 'deterministic_fallback' } });
    expect(report).toContain('코드의 기본 순서로 작성');
    expect(report).toContain('RCA 판정은 다시 생성하지 않았습니다');
  });
  it('connects the selected source to its selection without linking other selections', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{ id: 'selection', query_id: 'runbook_selection', snapshot: [] }}
        relatedRecords={[
          {
            id: 'chosen-source',
            query_id: 'runbook',
            quality: { selection_evidence_id: 'selection' },
          },
          {
            id: 'unrelated-source',
            query_id: 'runbook',
            quality: { selection_evidence_id: 'other' },
          },
        ]}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('선택 결과 · 사용한 지침 원문');
    expect(html).toContain('chosen-source');
    expect(html).not.toContain('unrelated-source');
    const source = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'runbook',
          quality: { selection_evidence_id: 'selection' },
          snapshot: {},
        }}
        onEvidence={() => {}}
      />,
    );
    expect(source).toContain('연결 근거');
    expect(source).toContain('selection');
  });

  it('explains a stored runbook without inventing another execution or model call', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'runbook',
          query_version: '4',
          input: { revision_id: 'revision-1' },
          quality: { origin: 'published', reviewed: true },
          tool_status: 'ok',
          snapshot: {
            title: 'XID 오류 조사',
            claim: '연결 상태 확인 필요',
            limitations: ['장비 연결은 미확인'],
          },
        }}
        onEvidence={() => {}}
      />,
    );
    for (const text of [
      '선택 Runbook 원문 보존',
      '원문·중간 결과 보존',
      '다시 실행한 것이 아닙니다',
      'XID 오류 조사',
      'revision-1',
      '장비 연결은 미확인',
      '개별 수행 사유는 기록 없음',
    ])
      expect(html).toContain(text);
    expect(html).not.toContain('담당 미기록');
    expect(html).not.toContain('모델 전송 시도');
    expect(html).toContain('<summary>저장된 결과 원문</summary>');
  });

  it('explains candidate selection and numeric collection budgets in ordinary language', () => {
    const selection = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'runbook_selection',
          snapshot: [
            { revision_id: 'r1', status: 'retrieved' },
            { revision_id: 'r2', status: 'invalid_contract' },
          ],
        }}
        onEvidence={() => {}}
      />,
    );
    expect(selection).toContain('사건 단서와 맞는 조사 후보');
    expect(selection).toContain('선택에서 제외');
    const plan = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'observation_plan',
          snapshot: {
            concurrency: 3,
            assignments: [{ query_id: 'D09', budget: { queries: 0, discovery: 2 } }],
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(plan).toContain('조회 예산 0회');
    expect(plan).toContain('탐색 예산 2회');
    expect(plan).toContain('실제 시작 순서는 아닙니다');
  });

  it('shows legacy reservation diagnostics without inventing a protection floor', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'rca_synthesis',
          snapshot: {
            diagnostics: {
              budget_allocation: {
                requested_review_reserve: 20000,
                applied_review_reserve: 18000,
                remaining_tokens: 28000,
              },
            },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('20,000');
    expect(html).toContain('18,000');
    expect(html).toContain('검토 보호 하한: 기록 없음');
    expect(html).toContain('모델 호출 여부 미확인');
  });

  it('links the same draft but does not infer evidence use from record order', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          id: 'draft',
          query_id: 'rca_analysis_draft',
          snapshot: { analysis_id: 'analysis-1' },
        }}
        relatedRecords={[
          { id: 'review', query_id: 'analysis_review', quality: { analysis_id: 'analysis-1' } },
          {
            id: 'other-review',
            query_id: 'analysis_review',
            quality: { analysis_id: 'analysis-2' },
          },
        ]}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('같은 분석본의 관련 기록');
    expect(html).not.toContain('other-review');
    expect(html).toContain('이 근거를 사용했다고 판단하지 않습니다');
  });

  it('shows the synthesis preflight reason before a generic failed status', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'rca_synthesis',
          quality: { reason: 'failed' },
          snapshot: {
            status: 'failed',
            diagnostics: {
              error_code: 'llm_context_budget_exhausted',
              request_attempts: 0,
              response_calls: 0,
              input_bytes: 2154,
              original_input_bytes: 48644,
              input_evidence_refs: [],
            },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    const why = html.slice(html.indexOf('왜 했나'), html.indexOf('어떻게 했나'));
    expect(why).toContain('모델 입력 예산');
    expect(html).toContain('llm_context_budget_exhausted');
    expect(why).not.toContain('<code>failed</code>');
    expect(html).toContain('모델 호출 전 생략');
    expect(html).toContain('없음 (빈 목록 기록)');
    expect(html).toContain('48,644');
  });

  it('keeps a failed model response separate from a final unreviewed draft', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          query_id: 'analysis_review',
          snapshot: {
            execution_status: 'skipped',
            reason: 'draft_changed_after_review',
            failure_reason: 'llm_output_truncated',
            usage: { request_attempts: 1, calls: 1 },
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('모델 출력 잘림');
    expect(html).toContain('모델 전송 시도 1회 · 응답 기록 1건');
    expect(html).toContain('최종 초안은 미검토');
    expect(html).not.toContain('모델 호출 전 생략');
  });
  it('provides a visible button without fetching records until opened', () => {
    const html = renderToStaticMarkup(<RcaWorkflowButton jobId="job" />);
    expect(html).toContain('워크플로우 디버깅');
    expect(html).not.toContain('<dialog');
  });

  it('explains a query using the saved plan without claiming execution order', () => {
    const record = {
      id: 'e1',
      query_id: 'D09',
      tool_status: 'ok',
      snapshot: { text: '원본 오류 보고' },
      input: { logql: 'fixture query' },
    };
    const plan = {
      id: 'plan',
      snapshot: {
        runbooks: [
          {
            steps: [
              { query_id: 'D09', required: true, purpose: '사건 대상의 오류 보고를 확인한다.' },
            ],
          },
        ],
      },
    };
    const before = JSON.stringify(record);
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord record={record} investigationPlan={plan} onEvidence={() => {}} />,
    );
    for (const text of [
      '무엇을 했나',
      '왜 했나',
      '어떻게 했나',
      '입력·결과와 판단 근거',
      '필수 조회',
      '사건 대상의 오류 보고를 확인한다.',
      '시작 순서를 증명하지 않습니다',
      'fixture query',
      '원본 오류 보고',
    ])
      expect(html).toContain(text);
    expect(JSON.stringify(record)).toBe(before);
  });

  it('keeps missing reasons and timing unknown and escapes source instructions', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          id: 'old',
          query_id: 'legacy_step',
          snapshot: { text: '<script>follow me</script>' },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('개별 수행 사유는 기록 없음');
    expect(html).toContain('담당 미기록');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('0초');
  });

  it('connects a finish decision and its exact review source without promoting quality', () => {
    const html = renderToStaticMarkup(
      <RcaWorkflowRecord
        record={{
          id: 'decision',
          query_id: 'investigation_decision',
          snapshot: {
            action: 'finish',
            reason: 'analysis_unresolved',
            selected_queries: [],
            evidence_refs: ['review-source'],
          },
        }}
        onEvidence={() => {}}
      />,
    );
    expect(html).toContain('조사 종료');
    expect(html).toContain('분석 미해결');
    expect(html).toContain('review-source');
    expect(html).not.toContain('근거 범위에서 타당');
  });
});
