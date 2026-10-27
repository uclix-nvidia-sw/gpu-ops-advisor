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

it.each(['ops-observation-diagnostics-v1', 'ops-observation-diagnostics-v2'])(
  'shows saved %s causes independently of AI and preserves legacy uncertainty',
  (version) => {
    const reason = '추가 조회 예산이 소진되어 연결 변경 검증을 실행하지 못함';
    const detail =
      'cpc-2 / batch / V100 · 현재 기간: 24시간 중 17시간을 활동률에 반영했습니다. ' +
      reason +
      ' 7시간.';
    const value = {
      result_status: 'partial',
      narrative_status: 'omitted',
      limitations: [detail],
      topics: [
        {
          topic_id: 'namespace_usage',
          status: 'partial',
          rows: [],
          quality: {
            observation_diagnostics: {
              version,
              summary: [reason],
              messages: [detail, '<script>private</script>'],
            },
          },
        },
      ],
    };
    const render = (data: unknown) =>
      renderToStaticMarkup(
        <MemoryRouter>
          <AggregateReport value={data as typeof value} />
        </MemoryRouter>,
      );
    const html = render(value);
    expect(html).toContain('활동률 산출·기간 비교의 제한');
    expect(html.indexOf(reason)).toBeLessThan(html.indexOf('대상·기간별 제외 사유 보기'));
    expect(html).toContain('검증 미실행은 신원 충돌이 확인됐다는 뜻이 아닙니다');
    expect(html.split(detail)).toHaveLength(2);
    expect(html).toContain('&lt;script&gt;private&lt;/script&gt;');
    expect(html).not.toContain('<script>private</script>');
    const old = render({
      ...value,
      limitations: [],
      topics: [{ topic_id: 'namespace_usage', status: 'partial', rows: [] }],
    });
    expect(old).not.toContain(reason);
    expect(old).not.toContain('부분 산출 원인');
  },
);

it('shows v2 Pod failures and previous-period budget limits before the AI interpretation', () => {
  const podReason = 'Pod 노드가 GPU 노드와 다르거나 미배정 구간이 연결 이전에 끝나지 않음';
  const budgetReason = '추가 조회 예산이 소진되어 연결 변경 검증을 실행하지 못함';
  const podDetail = `cluster-a / batch / A100 · 현재 기간: 24시간 중 23시간을 활동률에 반영했습니다. ${podReason} 1시간.`;
  const previousDetail = `cluster-b / batch / V100 · 이전 기간: 24시간 중 17시간을 활동률에 반영했습니다. ${budgetReason} 7시간.`;
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          result_status: 'partial',
          narrative_status: 'complete',
          quality: { report: { method: 'llm_interpreted' } },
          limitations: [podDetail, previousDetail],
          topics: [
            {
              topic_id: 'namespace_usage',
              status: 'partial',
              rows: [],
              quality: {
                observation_diagnostics: {
                  version: 'ops-observation-diagnostics-v2',
                  summary: [podReason, budgetReason],
                  messages: [podDetail, previousDetail],
                },
              },
            },
          ],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: 'GPU 활동을 관측했습니다.',
              meaning: '확인된 구간에 한해 해석합니다.',
              next_check: '추가 할당 전에 운영 조건을 확인하세요.',
            },
          ],
        }}
      />
    </MemoryRouter>,
  );
  const aiStart = html.indexOf('aria-label="namespace_usage AI 운영 해석"');
  expect(aiStart).toBeGreaterThan(0);
  for (const detail of [podDetail, previousDetail]) {
    expect(html).toContain(detail);
    expect(html.split(detail)).toHaveLength(2);
    expect(html.indexOf(detail)).toBeLessThan(aiStart);
  }
  for (const reason of [podReason, budgetReason]) {
    expect(html.indexOf(reason)).toBeLessThan(html.indexOf('대상·기간별 제외 사유 보기'));
  }
  expect(html).toContain('검증 미실행은 신원 충돌이 확인됐다는 뜻이 아닙니다');
});

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
  expect(html).toContain('1.1. Namespace별 비교');
  expect(html.replace(/<!-- -->/g, '')).toContain('2.1. 장애 종류별 발생 현황');
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

it('keeps saved interpretation timestamps and text intact when adding wrap boundaries', () => {
  const text =
    'cpc-1 / test-project-demand-forecast: 10/13 15:00~10/13 16:00 KST 0.00%\n다음 10/14 01:02:03에는 96.98%.';
  const value = {
    narrative_status: 'complete',
    quality: { report: { method: 'llm_interpreted' } },
    topics: [{ topic_id: 'namespace_usage' }],
    narrative: [
      {
        topic_id: 'namespace_usage',
        observation: text,
        meaning: '해석 유지',
        next_check: '확인 유지',
      },
    ],
  };
  const before = JSON.stringify(value);
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} onEvidence={() => {}} />
    </MemoryRouter>,
  );
  const observation = html.split('<dd>')[1].split('</dd>')[0];
  expect(observation).toContain(
    '<span class="aggregate-timestamp">10/13 15:00</span>~<span class="aggregate-timestamp">10/13 16:00</span>',
  );
  expect(observation).toContain('<span class="aggregate-timestamp">10/14 01:02:03</span>');
  expect(observation.replace(/<[^>]+>/g, '')).toBe(text);
  expect(JSON.stringify(value)).toBe(before);
  expect(html).toContain('<dd>해석 유지</dd>');
});

it('shows optional device memory without interpreting missing memory as zero', () => {
  const value = {
    topics: [
      {
        topic_id: 'namespace_usage',
        rows: [
          {
            cluster_id: 'cpc-1',
            namespace: 'service',
            gpu_model: 'A100',
            activity_percent: 0,
            hours: [],
            gpu_memory: { used_gib_per_gpu: 0, free_gib_per_gpu: 80 },
          },
          {
            cluster_id: 'cpc-2',
            namespace: 'batch',
            gpu_model: 'V100',
            hours: [],
            gpu_memory: { used_gib_per_gpu: null, free_gib_per_gpu: null },
          },
          {
            cluster_id: 'cpc-2',
            namespace: 'training',
            gpu_model: 'A100',
            hours: [],
            gpu_memory: { used_gib_per_gpu: 60, free_gib_per_gpu: 20 },
          },
        ],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} onEvidence={() => {}} />
    </MemoryRouter>,
  );
  expect(html).toContain('0.00 GiB');
  expect(html).toContain('80.00 GiB');
  expect(html).toContain('0.0%');
  expect(html).not.toContain('0.0% / 100.0%');
  expect(html).toContain('GPU 메모리 사용 비율');
  expect(html).toContain('사용 0.00 GiB / 전체 80.00 GiB');
  expect(html).toContain('75.0%');
  expect(html).toContain('사용 60.00 GiB / 전체 80.00 GiB');
  expect(html).toContain('aggregate-namespace-memory');
  expect(html).not.toContain('GPU 메모리 보조 관측');
  expect(html).toContain('확인 불가');
  expect(html).toContain('전용 사용량이나 할당량이 아닙니다');
});

it('distinguishes previous-only incident nodes and gives hidden captions accessible names', () => {
  const value = {
    topics: [
      {
        topic_id: 'incident_summary',
        summary: {
          count: 1,
          categories: [
            { cluster_id: 'cpc-2', name: 'XID 79', count: 0, previous_count: 2, nodes: [] },
            { cluster_id: 'cpc-1', name: 'XID 79', count: 1, previous_count: 0, nodes: [] },
          ],
          incidents: [],
        },
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} onEvidence={() => {}} />
    </MemoryRouter>,
  );
  expect(html).toContain('이번 기간 발생 없음');
  expect(html).toContain('노드 미확인');
  expect(html).toContain('<caption class="sr-only">');
});
it('shows waiting-only namespace workload observations and keeps missing completions unknown', () => {
  const value = {
    topics: [
      {
        topic_id: 'namespace_usage',
        rows: [],
        workloads: [
          {
            cluster_id: 'cpc-2',
            namespace: 'waiting-only',
            pending_peak: 2,
            unscheduled_peak: 1,
            running_peak: 0,
            completed_observed: null,
            mean_elapsed_seconds: null,
          },
        ],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} onEvidence={() => {}} />
    </MemoryRouter>,
  );
  expect(html).toContain('waiting-only');
  expect(html).toContain('자료 없음');
  expect(html).toContain('대기는 GPU 부족을 뜻하지 않습니다');
});

it('renders Namespace proposals with code observations, AI meaning and conditions', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          narrative_status: 'complete',
          quality: { report: { method: 'llm_interpreted' } },
          topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: 'verified observation',
              meaning: 'AI meaning',
              next_check: 'AI check',
              observation_source: 'calculated',
              advice: [
                {
                  fact_id: 'namespace-advice-0',
                  target: { cluster_id: 'cpc-2', namespace: 'long-project-namespace' },
                  recommendation: '작업 배치 제약 점검',
                  observation: '해당 구간 최대 대기 Pod 수 2개',
                  meaning: '대기는 있지만 할당 확대 근거는 부족합니다.',
                  next_check: '스케줄러 이벤트와 배치 제약을 대조하세요.',
                  conditions: '단일 날짜의 조건부 검토입니다.',
                },
              ],
              evidence_refs: ['proof'],
              value_refs: [],
              source_fact_ids: ['namespace-advice-0'],
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('aggregate-advice-groups');
  expect(html).toContain('long-project-namespace');
  expect(html).toContain('해당 구간 최대 대기 Pod 수 2개');
  expect(html).toContain('스케줄러 이벤트와 배치 제약을 대조하세요.');
  expect(html).toContain('단일 날짜의 조건부 검토입니다.');
  expect(html).toContain('근거 1 확인');
  expect(html).not.toContain('눈에 띄는 변화');
});

it('shows LLM bullet summaries before collapsed details without repeating advice labels', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        onEvidence={() => {}}
        value={{
          narrative_status: 'complete',
          quality: { report: { method: 'llm_interpreted' } },
          topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: 'code observation',
              meaning: 'AI meaning',
              next_check: 'AI check',
              advice: [
                {
                  fact_id: 'namespace-advice-0',
                  target: { cluster_id: 'cpc-1', namespace: 'long-project-name' },
                  summary:
                    'cpc-1 / long-project-name · 10/15 02:00~04:00: 활동이 적었습니다. 예약 일정을 확인한 뒤 이 시간대 배치 작업 실행을 검토하세요.',
                  observation: 'detailed observation',
                  meaning: 'detailed interpretation',
                  next_check: 'detailed check',
                  conditions: 'detailed condition',
                },
              ],
            },
          ],
        }}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('aggregate-namespace-summary');
  expect(html).toContain('AI가 작성한 요약');
  expect(html.indexOf('활동이 적었습니다')).toBeLessThan(html.indexOf('<details'));
  expect(html.indexOf('detailed observation')).toBeGreaterThan(html.indexOf('<details'));
  expect(html).not.toContain('<strong>운영 제안</strong>');
  expect(html).not.toContain('<strong>다음 확인</strong>');
});

it('shows stored selection criteria inside evidence details without changing the AI sentence', () => {
  const summary = 'cpc-2의 대기 변화와 배치 완료를 확인하세요.';
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          quality: { report: { method: 'llm_interpreted' } },
          narrative_status: 'complete',
          topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: '관측',
              meaning: '의미',
              next_check: '확인',
              advice: [
                {
                  fact_id: 'batch',
                  summary,
                  observation: '완료 표본 3건',
                  conditions: '대기·준비 포함 Job 경과시간',
                },
              ],
              selection: {
                eligible_count: 22,
                offered_count: 12,
                criteria: {
                  version: 'namespace-pattern-advice-v3',
                  high_activity_percent: 80,
                  low_activity_percent: 5,
                  minimum_pattern_hours: 2,
                },
              },
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain(summary);
  expect(html).toContain('선별 기준');
  expect(html).toContain('근거 후보 22개 중 12개');
  expect(html.indexOf(summary)).toBeLessThan(html.indexOf('해석 근거와 계산 결과'));
  expect(html.indexOf('선별 기준')).toBeGreaterThan(html.indexOf('해석 근거와 계산 결과'));
});

it.each([
  ['spaced', true],
  ['unspaced', true],
  ['invalid', false],
] as const)('uses only exact stored summary slices (%s)', (variant, matching) => {
  const decision = '다른 작업을 넣기 전에 상주 메모리 유지 필요성을 확인하세요.';
  const evidence = 'cpc-1 / serving · 10/19 02:00~10/19 05:00 KST: 활동률 0.36%, 메모리 98%입니다.';
  const summary = variant === 'unspaced' ? `${decision}${evidence}` : `${decision} ${evidence}`;
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          quality: { report: { method: 'llm_interpreted' } },
          narrative_status: 'complete',
          topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: '관측',
              meaning: '의미',
              next_check: '점검',
              advice: [
                {
                  fact_id: 'memory',
                  target: { cluster_id: 'cpc-1', namespace: 'serving' },
                  summary,
                  summary_parts: { decision: matching ? decision : 'changed', evidence },
                  observation: '계산한 장치 관측',
                  conditions: 'Namespace 전용 사용량이 아닙니다.',
                  evidence_refs: ['source-a'],
                },
              ],
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('판단 근거와 적용 조건');
  expect(html).toContain('원본 근거 1');
  expect(html).toContain('Namespace 전용 사용량이 아닙니다.');
  expect(html).not.toContain('changed');
  expect(html).toContain(
    '<h3 class="aggregate-advice-card-title">AI 운영 해석</h3><p class="aggregate-advice-cluster-target"><span>대상 클러스터 :</span> <code>cpc-1</code></p>',
  );
  expect(html).toContain(
    '<h4 class="aggregate-advice-identity"><span>네임스페이스</span><span aria-hidden="true">:</span>',
  );
  expect(html).toContain('<code>cpc-1</code>');
  expect(html).toContain('<code>serving</code>');
  expect(html.indexOf(decision)).toBeLessThan(html.indexOf('aggregate-advice-target'));
  if (matching) {
    expect(html.indexOf(decision)).toBeLessThan(html.indexOf('<details'));
    expect(html.indexOf('활동률 0.36%')).toBeGreaterThan(html.indexOf('<details'));
    expect(html).toContain('aggregate-advice-target');
  } else {
    expect(html.indexOf('활동률 0.36%')).toBeLessThan(html.indexOf('<details'));
    expect(html).toContain('aggregate-advice-target');
  }
});

it.each([
  ['repeated_activity', '10/19 18:00~10/19 19:00 KST / 10/19 21:00~10/19 22:00 KST'],
  ['relative_activity', '후보 10/19 21:00~10/19 23:00 KST, 비교 10/19 19:00~10/19 21:00 KST'],
])('preserves separate observation and comparison periods (%s)', (kind, periods) => {
  const decision = '대상과 실행 조건을 대조하세요.';
  const evidence = `cpc-1 / example · ${periods}: 관측 근거입니다.`;
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          quality: { report: { method: 'llm_interpreted' } },
          narrative_status: 'complete',
          topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
          narrative: [
            {
              topic_id: 'namespace_usage',
              observation: '관측',
              meaning: '의미',
              next_check: '점검',
              advice: [
                {
                  fact_id: kind,
                  kind,
                  period: { start: '2026-10-19T12:00:00Z', end: '2026-10-19T14:00:00Z' },
                  reference_period: { start: '2026-10-19T10:00:00Z', end: '2026-10-19T12:00:00Z' },
                  target: { cluster_id: 'cpc-1', namespace: 'example' },
                  gpu_models: ['A100'],
                  summary: `${decision} ${evidence}`,
                  summary_parts: { decision, evidence },
                  observation: evidence,
                  conditions: '구간 사이의 관측을 추정하지 않습니다.',
                  evidence_refs: ['source'],
                },
              ],
            },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  const visible = html.replace(/<\/?span[^>]*>/g, '');
  expect(visible).toContain(periods);
  const heading = html.slice(html.indexOf('class="aggregate-advice-heading"'), html.indexOf('<dl'));
  expect(heading).not.toContain('GPU 모델');
  expect(html.indexOf('GPU 모델 · A100')).toBeGreaterThan(html.indexOf(decision));
  expect(html.indexOf('GPU 모델 · A100')).toBeLessThan(html.indexOf('<details'));
  expect(html).not.toContain('aggregate-advice-tag');
  expect(visible.indexOf(decision)).toBeLessThan(visible.indexOf('<details'));
  expect(visible.indexOf(periods)).toBeGreaterThan(visible.indexOf('<details'));
  expect(html).toContain('구간 사이의 관측을 추정하지 않습니다.');
  expect(html.includes('이미 지난 구간입니다.')).toBe(kind === 'relative_activity');
  if (kind === 'relative_activity') {
    expect(html.indexOf(decision)).toBeLessThan(html.indexOf('aggregate-advice-scope'));
    expect(html.indexOf('aggregate-advice-scope')).toBeLessThan(html.indexOf('<details'));
    const firstView = html.slice(0, html.indexOf('<details'));
    expect(firstView).toContain('작업 시간대 비교·시험 검토');
    expect(firstView).toContain('과거 관측');
    expect(firstView).toContain('낮은 활동 구간');
    expect(firstView).toContain('비교 구간');
    expect(firstView.indexOf('<dt>비교 구간</dt>')).toBeLessThan(
      firstView.indexOf('<dt>낮은 활동 구간</dt>'),
    );
    expect(firstView).not.toContain('같은 날의 두 구간을 비교한 시험 후보입니다.');
    expect(html.slice(html.indexOf('<details'))).toContain(
      '같은 날의 두 구간을 비교한 시험 후보입니다.',
    );
    expect(firstView).toContain('2026. 10. 19. 21:00');
    expect(firstView).toContain('2026. 10. 19. 19:00');
    expect(firstView).toContain(
      '과거 관측입니다. 향후 시간대 변경은 반복성과 실행 조건을 확인한 뒤 판단하세요.',
    );
    expect(html.slice(html.indexOf('<details'))).toContain('이미 지난 구간입니다.');
    expect(html.slice(html.indexOf('<details'))).toContain(
      '활동률이 낮은지와 사용 가능한 GPU를 확인한 뒤, 시작 시간을 바꿀 수 있는 작업 일부만',
    );
    expect(firstView).toContain('끝 시각은 포함하지 않습니다.');
  }
  expect(html.indexOf('<code>example</code>')).toBeLessThan(html.indexOf(decision));
});

it.each([
  ['relative_activity', undefined, undefined, 2],
  ['relative_activity', { start: 'bad', end: 'bad' }, undefined, 2],
  [
    'relative_activity',
    { start: '2026-10-20T01:00:00Z', end: '2026-10-20T00:00:00Z' },
    undefined,
    2,
  ],
  [
    'schedule_candidate',
    { start: '2026-10-20T00:00:00Z', end: '2026-10-20T02:00:00Z' },
    undefined,
    0,
  ],
  [
    'schedule_candidate',
    { start: '2026-10-19T20:00:00Z', end: '2026-10-19T22:00:00Z' },
    undefined,
    0,
  ],
  [
    'schedule_candidate',
    { start: '2026-10-19T14:00:09Z', end: '2026-10-19T16:00:17Z' },
    undefined,
    0,
  ],
])('keeps trial windows accurate (%s)', (kind, period, reference_period, unknownCount) => {
  const value = {
    quality: { report: { method: 'llm_interpreted' } },
    narrative_status: 'complete',
    topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
    narrative: [
      {
        topic_id: 'namespace_usage',
        observation: '저장된 관측',
        meaning: '원문을 바꾸지 않습니다.',
        next_check: '조건 확인',
        advice: [
          {
            fact_id: 'trial',
            kind,
            period,
            reference_period,
            target: { cluster_id: 'cpc-2', namespace: 'service' },
            summary: '원문을 바꾸지 않습니다.',
          },
        ],
      },
    ],
  };
  const before = JSON.stringify(value);
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} />
    </MemoryRouter>,
  );
  expect((html.match(/시간 범위 미확인/g) || []).length).toBe(unknownCount);
  expect(html).toContain('원문을 바꾸지 않습니다.');
  expect(html).toContain(
    kind === 'relative_activity' ? '작업 시간대 비교·시험 검토' : '작업 시간대 시험 검토',
  );
  expect(html).toContain('과거 관측');
  expect(html.includes('<dt>비교 구간</dt>')).toBe(kind === 'relative_activity');
  if (period?.start === '2026-10-19T20:00:00Z') {
    expect(html).toContain('(2026. 10. 20. 05:00 ~ 07:00 KST)');
  }
  if (period?.start === '2026-10-19T14:00:09Z') {
    const text = html.replace(/<[^>]*>/g, '');
    expect(text).toContain('2026. 10. 19. 23:00:09');
    expect(text).toContain('2026. 10. 20. 01:00:17');
  }
  expect(JSON.stringify(value)).toBe(before);
});

it('frames the stored report like the RCA report card with a fixed heading', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={{ topics: [], narrative: [] }} />
    </MemoryRouter>,
  );
  expect(html).toContain('<section id="final-report" class="aggregate-report rca-narrative"');
  expect(html).toContain('<header class="rca-narrative-header"><h3>운영 분석 보고서</h3>');
});

it('uses an independent original-style AI card for each selected cluster', () => {
  const value = {
    narrative_status: 'complete',
    quality: { report: { method: 'llm_interpreted' } },
    topics: [{ topic_id: 'namespace_usage', rows: [], findings: [] }],
    narrative: [
      {
        topic_id: 'namespace_usage',
        observation: '관측',
        meaning: '의미',
        next_check: '확인',
        advice: [
          {
            fact_id: 'service',
            target: { cluster_id: 'cpc-2', namespace: 'service' },
            kind: 'schedule_candidate',
            summary: 'stored service advice',
          },
          {
            fact_id: 'capacity',
            target: { cluster_id: 'cpc-1', namespace: 'batch' },
            kind: 'capacity_review',
            summary: 'stored capacity advice',
          },
          {
            fact_id: 'complete',
            target: { cluster_id: 'cpc-1', namespace: 'batch' },
            kind: 'batch_progress',
            summary: 'stored completion advice',
          },
        ],
      },
    ],
  };
  const original = JSON.stringify(value);
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} />
    </MemoryRouter>,
  );
  expect(html.match(/class="aggregate-advice-cluster"/g)).toHaveLength(2);
  expect(html).toContain('aria-label="cpc-1 클러스터 AI 운영 해석"');
  expect(html).toContain('aria-label="cpc-2 클러스터 AI 운영 해석"');
  expect(html).toContain(
    '<h3 class="aggregate-advice-card-title">AI 운영 해석</h3><p class="aggregate-advice-cluster-target"><span>대상 클러스터 :</span> <code>cpc-1</code></p>',
  );
  expect(html.indexOf('cpc-1 클러스터 AI 운영 해석')).toBeLessThan(
    html.indexOf('cpc-2 클러스터 AI 운영 해석'),
  );
  expect(html.indexOf('stored capacity advice')).toBeLessThan(
    html.indexOf('stored completion advice'),
  );
  expect(html.match(/class="aggregate-advice-namespace"/g)).toHaveLength(2);
  expect(html.match(/<strong>작성 방식<\/strong>/g)).toHaveLength(1);
  expect(JSON.stringify(value)).toBe(original);
});

it.each([false, true])(
  'keeps unattributed quality wording tied to the saved basis: %s',
  (current) => {
    const value = {
      result_status: current ? 'ready' : 'partial',
      topics: [
        {
          topic_id: 'namespace_usage',
          status: current ? 'ready' : 'partial',
          rows: [{ cluster_id: 'cpc-1', namespace: '', gpu_model: 'A100', hours: [] }],
          quality: current
            ? {
                namespace_status_basis: 'attributed_rows_with_current_cluster_coverage_v1',
                observation_diagnostics: {
                  version: 'ops-observation-diagnostics-v3',
                  summary: [],
                  messages: [],
                  unattributed_messages: ['Namespace 귀속 미확인'],
                },
              }
            : {},
        },
      ],
    };
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AggregateReport value={value} />
      </MemoryRouter>,
    );
    expect(html).toContain('Namespace에 연결하지 못한 관측');
    expect(html).not.toContain('부분 산출 원인');
    expect(html.includes('Namespace 활동 판정에 포함하지 않습니다')).toBe(current);
    expect(html.includes('전체 GPU 귀속의 완전성은 확인하지 않았습니다')).toBe(current);
    expect(html.includes('Namespace별 사용량 비교에서 제외했습니다')).toBe(!current);
  },
);

it.each([
  '추가 조회 예산이 소진되어 연결 변경 검증을 실행하지 못함',
  '후속 메모리·작업·문맥 수집과 수집기 검증의 최대 조회 예산을 남기기 위해 연결 변경 검증을 실행하지 않음',
])('shows the saved skip reason without replacing it: %s', (reason) => {
  const value = {
    topics: [
      {
        topic_id: 'namespace_usage',
        rows: [],
        quality: {
          observation_diagnostics: {
            version: 'ops-observation-diagnostics-v3',
            summary: [reason],
            messages: [`cpc-2: ${reason}`],
          },
        },
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport value={value} />
    </MemoryRouter>,
  );
  expect(html).toContain(reason);
  expect(html).toContain(`cpc-2: ${reason}`);
});

it.each([
  'selected',
  'unknown',
  'legacy',
  'missing-facts',
  'mismatched-target',
  'multiple-clusters',
])(
  'puts incident AI prose first for %s while retaining saved evidence and legacy display',
  (state) => {
    const section = {
      topic_id: 'incident_summary',
      observation_source: 'calculated',
      observation: 'XID 79: dgx01 5건 · dgx02 3건.',
      meaning: '같은 종류가 두 노드에서 관측됐습니다.',
      next_check: '기존 점검 기록과 발생 순서를 확인하세요.',
      source_fact_ids: ['other', 'selected'],
      evidence_refs: ['source-1'],
      interpretation_limit: '저장된 근거의 범위에서만 해석합니다.',
      ...(state === 'legacy'
        ? {}
        : { check_target: state === 'unknown' ? '' : 'cpc-1 / dgx01 / XID 79 · 저장 사건 5건' }),
    };
    const metric = {
      id: 'incident_summary.node_alert_count.0',
      period: { start: '2026-10-25T15:00:00Z', end: '2026-10-26T15:00:00Z' },
    };
    const value = {
      narrative_status: 'complete',
      quality: { report: { method: 'llm_interpreted' } },
      topics: [
        {
          topic_id: 'incident_summary',
          metrics: [metric],
          findings:
            state === 'missing-facts'
              ? []
              : [
                  {
                    id: 'other',
                    target: {
                      cluster_id: state === 'multiple-clusters' ? 'cpc-2' : 'cpc-1',
                      node: 'other-node',
                      alert_type: 'XID 13',
                    },
                  },
                  {
                    id: 'selected',
                    target: {
                      cluster_id: 'cpc-1',
                      node: state === 'mismatched-target' ? 'different-node' : 'dgx01',
                      alert_type: 'XID 79',
                    },
                    value_refs: [metric.id],
                  },
                ],
        },
      ],
      narrative: [section],
    };
    const before = JSON.stringify(value);
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AggregateReport value={value} onEvidence={() => {}} />
      </MemoryRouter>,
    );
    expect(JSON.stringify(value)).toBe(before);
    for (const text of [section.observation, section.meaning, section.next_check])
      expect(html.split(text)).toHaveLength(2);
    if (state === 'legacy') {
      const fields = [...html.matchAll(/<dt>(.*?)<\/dt>/g)].map((match) => match[1]);
      expect(fields).toEqual(['계산으로 확인한 관측', '의미와 한계', '확인할 점']);
      expect(html).not.toContain('자동 선정');
      expect(html).not.toContain('판단 근거와 확인 범위');
    } else {
      const [lead, rest] = html.split('<details class="aggregate-advice-evidence">');
      const evidence = rest.split('</details>')[0];
      expect(lead).toContain('aggregate-advice-cluster');
      expect(lead).toContain('aggregate-advice-identity');
      expect(lead).toContain(section.meaning + ' ' + section.next_check);
      expect(lead).not.toContain(section.observation);
      expect(lead).not.toContain('저장 사건 5건');
      expect(lead).not.toContain('자동 집계');
      expect(evidence).toContain('판단 근거와 확인 범위');
      expect(evidence).toContain(section.observation);
      expect(evidence).toContain(section.interpretation_limit);
      expect(evidence).toContain('해석 기준');
      expect(evidence).toContain('근거 1 확인');
      expect(evidence).toContain(
        section.check_target || '노드가 확인된 사건이 없어 선정하지 않았습니다.',
      );
      expect(html).toContain('본문은 AI 작성 · 관측 근거와 확인 대상은 자동 집계·선정');
      expect(html).not.toContain('<details class="aggregate-advice-evidence" open');
      if (['missing-facts', 'mismatched-target'].includes(state)) {
        expect(lead).toContain('저장된 확인 대상은 아래 근거에서 확인하세요.');
        expect(lead).not.toContain('different-node');
      } else if (state === 'unknown') {
        expect(lead).toContain('노드가 확인된 사건이 없어 선정하지 않았습니다.');
      } else {
        expect(lead).toContain(
          state === 'multiple-clusters'
            ? '<code>cpc-1 / dgx01 / XID 79</code>'
            : '<code>dgx01 / XID 79</code>',
        );
        expect(lead).toContain('분석 기간');
        expect(lead).not.toContain('other-node');
      }
    }
  },
);
