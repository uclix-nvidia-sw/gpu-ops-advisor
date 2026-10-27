import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RcaWorkflowRecord } from './RcaWorkflow';

const render = (query_id: string, snapshot: Record<string, unknown>) =>
  renderToStaticMarkup(<RcaWorkflowRecord record={{ query_id, snapshot }} onEvidence={() => {}} />);

describe('code decision trace', () => {
  it('shows actual zero/null inputs, the executed condition and its output before raw JSON', () => {
    const html = render('collection_assessment', {
      schema: 'rca-code-decision/1',
      source: 'rcca_agent.workflow.evaluate_requirements',
      inputs: { collected_queries: ['D09'] },
      outputs: {
        alert_match: { status: 'event_not_found' },
        gaps: ['event_not_found'],
        gate: 'sufficient',
      },
      checks: [
        {
          rule: 'preceding_healthy',
          expression: 'len(healthy) > 0',
          value: false,
          inputs: {
            preceding_healthy_count: 0,
            last_healthy_at: null,
            first_unhealthy_at: '2026-10-26T07:37:24Z',
          },
        },
      ],
      evidence_refs: ['evidence-one'],
    });
    const panel = html.slice(
      html.indexOf('aria-label="코드 판정 과정"'),
      html.indexOf('결과·남은 한계'),
    );
    expect(panel).toContain('조건 불성립 (false)');
    expect(panel).toContain('len(healthy) &gt; 0');
    expect(panel).toContain('<dd>0</dd>');
    expect(panel).toContain('null · 값 없음');
    expect(panel).toContain('event_not_found');
    expect(panel).toContain('재전환은 이 조건에 반영하지 않습니다');
    expect(panel).toContain('근거 1');
    expect(html).toContain('수집 결과 코드 판정');
    expect(html.indexOf('aria-label="코드 판정 과정"')).toBeLessThan(html.indexOf('무엇을 했나'));
  });

  it.each(['ready', 'partial', 'blocked'])(
    'shows saved %s status rather than inferring from missing inputs',
    (status) => {
      const html = render('rca_status_decision', {
        schema: 'rca-code-decision/1',
        inputs: { analysis_status: 'failed', result_rule: 'stored rule' },
        outputs: {
          result_status: status,
          missing_inputs: ['synthesis_failed'],
          assessments: [{ assessment_id: 'book', status, missing_inputs: ['synthesis_failed'] }],
        },
      });
      expect(html).toContain(`>${status}<`);
      expect(html).toContain('synthesis_failed');
      expect(html).toContain('stored rule');
      expect(html).toContain('최종 산출 상태 판정');
    },
  );

  it('keeps historical conclusions but explicitly marks unavailable execution inputs', () => {
    const html = render('rca_result_frozen', {
      material: {
        missing_inputs: ['event_not_found'],
        analysis: { alert_match: { status: 'event_not_found' } },
      },
    });
    expect(html).toContain('독립 실행 기록이 없습니다');
    expect(html).toContain('조건별 입력·분기와 적용 코드 버전은 미기록');
    expect(html).toContain('event_not_found');
    expect(html).not.toContain('조건 불성립 (false)');
    expect(html).not.toContain('preceding_healthy_count');
  });

  it('links both new decision records from the frozen material', () => {
    const html = render('rca_result_frozen', {
      decision_evidence_refs: ['collection', 'status'],
      material: {},
    });
    expect(html).toContain('수집 결과 코드 판정 열기');
    expect(html).toContain('최종 산출 상태 판정 열기');
    expect(html).not.toContain('독립 실행 기록이 없습니다');
  });

  it('does not pretend missing historical fields were empty or successful', () => {
    const html = render('rca_result_frozen', {});
    expect(html).toContain('미기록');
    expect(html).not.toContain('[] · 빈 목록');
  });
});
