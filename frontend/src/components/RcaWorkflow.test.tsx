import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RcaWorkflowButton, RcaWorkflowRecord } from './RcaWorkflow';

describe('developer RCA workflow entry and evidence', () => {
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
