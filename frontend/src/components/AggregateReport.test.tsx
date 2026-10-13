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
