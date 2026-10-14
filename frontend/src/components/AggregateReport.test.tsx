import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import {
  AggregateReport,
  namespaceGroups,
  namespaceActivity,
  incidentShortTitle,
} from './AggregateReport';
import { aggregatePeriod } from '../pages/AggregateReportForm';

it('renders observed zero separately from missing observations and comparison', () => {
  const row = {
    cluster_id: 'cpc-1',
    namespace: 'test-dept-service',
    gpu_model: 'A100',
    activity_percent: 0,
    previous_activity_percent: null,
    change_percentage_points: null,
    valid_hours: 1,
    expected_hours: 24,
    low_activity_hours: null,
    hours: [
      {
        start: '2026-10-11T15:00:00Z',
        end: '2026-10-11T16:00:00Z',
        activity_percent: 0,
        reasons: [],
      },
      {
        start: '2026-10-11T16:00:00Z',
        end: '2026-10-11T17:00:00Z',
        activity_percent: null,
        reasons: ['unobserved_hour'],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{ topics: [{ topic_id: 'namespace_usage', rows: [row], findings: [] }] }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('0.00%');
  expect(html).toContain('산출 불가');
  expect(html).toContain('비교 보류');
  expect(html).toContain('이 시간대 관측 없음');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain('role="img"');
});
it('keeps an empty incident period distinct from hardware health', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          topics: [
            { topic_id: 'incident_summary', summary: { count: 0, incidents: [], groups: [] } },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('저장된 사건이 없습니다');
  expect(html).toContain('장비 전체의 무장애를 뜻하지 않습니다');
});
it('builds complete KST days across month boundaries', () => {
  expect(aggregatePeriod('2026-10-02', 'weekly')).toEqual({
    start: '2026-09-25T15:00:00.000Z',
    end: '2026-10-02T15:00:00.000Z',
  });
  expect(aggregatePeriod('2026-10-02', 'daily')).toEqual({
    start: '2026-10-01T15:00:00.000Z',
    end: '2026-10-02T15:00:00.000Z',
  });
});

it('groups namespace rows within each cluster and keeps models as details', () => {
  const first = {
    cluster_id: 'cpc-1',
    namespace: 'runai-test1',
    nodes: ['dgx01'],
    gpu_model: 'A100 40GB',
    quality_status: 'ready',
    observed_gpu_count: 4,
    valid_hours: 24,
    expected_hours: 24,
    activity_percent: 0.4,
    previous_activity_percent: 0.3,
    previous_valid_hours: 12,
    previous_expected_hours: 24,
    comparison_status: 'insufficient_observation',
    hours: [{ activity_percent: 0.4, gpu_ids: ['g1', 'g2', 'g3', 'g4'] }],
  };
  const second = {
    ...first,
    gpu_model: 'A100 80GB',
    activity_percent: 9.2,
    hours: [{ activity_percent: 9.2, gpu_ids: ['g5', 'g6', 'g7', 'g8'] }],
  };
  const data = [first, second, { ...first, cluster_id: 'cpc-2' }, { ...first, namespace: '' }];
  expect(namespaceGroups(data).map((g) => g.models.length)).toEqual([2, 1]);
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{ topics: [{ topic_id: 'namespace_usage', rows: data, findings: [] }] }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('8개');
  expect(html).not.toContain('Namespace 활동과 운영 변화');
  expect(html).toContain('<h2 id="namespace-summary-title">');
  const table = html.split('<table class="aggregate-namespace-table">')[1].split('</table>')[0];
  expect(table).not.toContain('checkbox');
  expect(table).not.toContain('그래프 표시');
  expect(html).toContain('<details class="aggregate-model-detail"><summary>세부 수치와 자료 상태');
  expect(html).toContain('관측 노드');
  expect(html).toContain('dgx01');
  expect(html).toContain('0.40%');
  expect(html).toContain('9.20%');
  expect(html).toContain('이전 12/24시간 확인');
  expect(html).toContain('Namespace에 연결하지 못한 관측');
  // The same UUID crossing models must not inflate the namespace count.
  const overlap = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          topics: [
            {
              topic_id: 'namespace_usage',
              rows: [first, { ...second, hours: first.hours }],
              findings: [],
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(overlap).not.toContain('8개');
});

it('shows incident content and cannot turn missing GPU identity into no repetition', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          topics: [
            {
              topic_id: 'incident_summary',
              summary: {
                count: 2,
                status_as_of: '2026-10-13T06:29:46Z',
                unclassified_count: 2,
                categories: [
                  {
                    cluster_id: 'cpc-1',
                    name: 'XID 79',
                    nodes: ['dgx01'],
                    count: 2,
                    previous_count: 1,
                    firing_count: 1,
                    test_count: 1,
                  },
                ],
                incidents: [
                  {
                    id: 'a',
                    cluster_id: 'cpc-1',
                    symptom: 'XID 79 GPU fallen off bus',
                    occurred_at: '2026-10-13T05:27:10Z',
                    target: { node: 'dgx01' },
                    alarm_status: 'firing',
                    result_id: 'published-result',
                  },
                  { id: 'b', cluster_id: 'cpc-1', symptom: null },
                ],
              },
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).not.toContain('XID 79 GPU fallen off bus');
  expect(html).toContain('dgx01');
  expect(html).toContain('미확인 사건은 반복 그룹 수에 포함되지 않습니다');
  expect(html).toContain('장애 설명 미저장');
  expect(html).toContain('시험 표시');
  expect(html).toContain('XID 79 · GPU 연결 끊김 알림');
  expect(html).not.toContain('알림 원문');
  expect(html).toContain('<th>클러스터</th><th>노드</th><th>알림 내용</th>');
  expect(html).toContain('badge-firing');
  expect(html).toContain('알림 상태<span>작성 기준</span>');
  expect(html).toContain('현재 상태와 다를 수 있습니다');
  expect(html).toContain('2026. 10. 13. 15:29:46 KST');
  expect(html).toContain('<td>cpc-1</td><td>dgx01</td>');
  expect(html).toContain('<td>cpc-1</td><td>미확인</td>');
  expect(html).toContain('RCA 보기');
  expect(html).toContain('사건 보기');
  expect(html).toContain('RCA 미발행');
  expect((html.match(/href="\/incidents\/a"/g) || []).length).toBe(1);
  expect((html.match(/href="\/incidents\/b"/g) || []).length).toBe(1);
  expect((html.match(/class="text-link"/g) || []).length).toBe(2);
  expect(html).toContain('<span>2026. 10. 13.</span><span>14:27:10</span>');
});

it('shows model mean ranges without averaging models or inventing missing activity', () => {
  expect(namespaceActivity([{ activity_percent: 0 }, { activity_percent: null }])).toBe('0.00%');
  expect(namespaceActivity([{ activity_percent: 0.51 }, { activity_percent: 6.09 }])).toBe(
    '0.51%–6.09%',
  );
  expect(namespaceActivity([{ activity_percent: NaN }, { activity_percent: null }])).toBe(
    '산출 불가',
  );
});
it('shortens known alert wording while keeping unknown titles bounded and accurate', () => {
  expect(
    incidentShortTitle(
      'XID 79 ROBUST_CHANNEL_GPU_HAS_FALLEN_OFF_THE_BUS GPU has fallen off the bus detected on GPU PCI:0000:01:00',
    ),
  ).toBe('XID 79 · GPU 연결 끊김 알림');
  expect(
    incidentShortTitle('SXID 11001(ingress invalid command) detected on PCI:0000:00:00.0'),
  ).toContain('스위치 수신 명령 오류');
  expect(incidentShortTitle('XID 79 unrecognized wording')).toBe('XID 79 unrecognized wording');
  expect(incidentShortTitle('')).toContain('미저장');
  expect(incidentShortTitle('a'.repeat(80))).toBe('a'.repeat(60) + '…');
});

it('does not invent a status timestamp for an older stored report', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          topics: [
            {
              topic_id: 'incident_summary',
              summary: { count: 1, incidents: [{ id: 'old', alarm_status: 'resolved' }] },
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('기준 시각: 미저장');
  expect(html).toContain('현재 상태와 다를 수 있습니다');
  expect(html).not.toContain('badge-firing');
});

it.each([
  ['complete', 'llm_prioritized', 'AI가 고른 주요 변화', true],
  ['failed', 'deterministic_fallback', '계산 결과 요약', false],
  ['omitted', 'deterministic_fallback', '계산 결과 요약', false],
  ['complete', undefined, '저장된 주요 변화', false],
  ['failed', 'llm_prioritized', '저장된 주요 변화', false],
])('labels summary provenance for %s / %s without rewriting facts', (status, method, title, ai) => {
  const html = renderToStaticMarkup(
    <AggregateReport
      value={{
        narrative_status: status,
        quality: { report: { method } },
        narrative: [{ id: 'finding-1', summary_text: '계산한 활동률은 12.34%입니다.' }],
      }}
      onEvidence={() => {}}
    />,
  );
  expect(html).toContain(title);
  expect(html).toContain('계산한 활동률은 12.34%입니다.');
  expect(html.includes('aggregate-summary-ai')).toBe(ai);
  if (ai) expect(html).toContain('AI가 원인이나 운영 조치를 판단한 내용은 아닙니다.');
});
it('does not invent an AI summary when saved narrative is empty', () => {
  const html = renderToStaticMarkup(
    <AggregateReport
      value={{
        narrative_status: 'complete',
        quality: { report: { method: 'llm_prioritized' } },
        narrative: [],
      }}
      onEvidence={() => {}}
    />,
  );
  expect(html).not.toContain('report-summary-title');
});

it('shows generated interpretations inside each topic with source facts and snapshot limits', () => {
  const topicIds = ['namespace_usage', 'incident_summary'];
  const value = {
    narrative_status: 'complete',
    quality: { report: { method: 'llm_interpreted' } },
    topics: topicIds.map((topic_id) => ({
      topic_id,
      findings: [{ id: topic_id + '-fact', text: topic_id + ' calculated fact' }],
      metrics:
        topic_id === 'namespace_usage'
          ? [
              {
                id: 'namespace_usage.hourly_activity.7',
                value: 75,
                target: { cluster_id: 'cpc-1', namespace: 'research', model: 'A100' },
                period: { start: '2026-10-13T01:00:00Z', end: '2026-10-13T02:00:00Z' },
              },
            ]
          : [],
    })),
    narrative: topicIds.map((topic_id) => ({
      id: topic_id,
      topic_id,
      observation: topic_id + ' observed change',
      meaning: '확인된 범위에서만 해석합니다.',
      next_check: '기존 기록을 확인해 보세요.',
      interpretation_limit: '알림 상태는 보고서 작성 당시 기준입니다.',
      source_fact_ids: [topic_id + '-fact'],
      value_refs: ['namespace_usage.hourly_activity.7'],
      evidence_refs: [topic_id + '-evidence'],
    })),
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} onEvidence={() => {}} />
    </MemoryRouter>,
  );
  expect(html.match(/<h3>AI 운영 해석<\/h3>/g)).toHaveLength(2);
  expect(html).not.toContain('id="report-summary-title"');
  expect(html).toContain('해석 근거와 계산 결과');
  expect(html).toContain('namespace_usage calculated fact');
  expect(html).toContain('incident_summary calculated fact');
  expect(html).toContain('근거 1 확인');
  expect(html).toContain('75.00%');
  expect(html).toContain('research');
  expect(html).toContain('10:00');
  expect(html).toContain('보고서 작성 당시');
  expect(html).toContain('실제 조치나 장애 원인 판정이 아닙니다');
  expect(html.indexOf('namespace-summary-title">')).toBeLessThan(
    html.indexOf('namespace_usage observed change'),
  );
  expect(html.indexOf('incident-summary-title">')).toBeLessThan(
    html.indexOf('incident_summary observed change'),
  );
});
it('does not call failed or unlabelled prose an AI interpretation', () => {
  for (const narrative_status of ['failed', 'omitted']) {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AggregateReport
          value={{
            narrative_status,
            quality: { report: { method: 'llm_interpreted' } },
            topics: [{ topic_id: 'namespace_usage' }],
            narrative: [{ id: 'n', text: 'stored summary' }],
          }}
          onEvidence={() => {}}
        />
      </MemoryRouter>,
    );
    expect(html).not.toContain('<h3>AI 운영 해석</h3>');
    expect(html).toContain('stored summary');
  }
});
