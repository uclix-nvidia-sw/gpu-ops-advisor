import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReportContent } from '../components/ReportContent';
import {
  reportObservations,
  metricValue,
  metricUnit,
  collectionStatus,
  collectionNextCheck,
} from './report';
import { DataView, QueryState } from '../components/live';

describe('report presentation', () => {
  it('shows the complete final report despite missing metrics or LLM failure', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        value={{
          result_status: 'blocked',
          narrative_status: 'failed',
          topics: [],
          narrative: [
            {
              id: 'scope',
              title: '분석 범위와 결과',
              text: '원인 미확인\n\n<script>unsafe</script>',
              value_refs: [],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('id="final-report"');
    expect(html).toContain('GPU Ops 최종 보고서');
    expect(html).toContain('기본 보고서');
    expect(html).toContain('원인 미확인');
    expect(html).not.toContain('<script>');
  });
  it('shows usable observations, unknown allocation and escaped targets separately', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        value={{
          result_status: 'partial',
          narrative_status: 'omitted',
          evidence_refs: ['e1'],
          topics: [
            {
              topic_id: 'O02',
              status: 'partial',
              missing_inputs: ['allocation_contract_missing'],
              metrics: [
                {
                  id: 'O02.mapped_gpu_hours',
                  value: 7.9864,
                  unit: 'GPU-hours',
                  target: { namespace: '<script>bad</script>' },
                },
                {
                  id: 'O02.allocated_gpu_hours',
                  value: null,
                  quality: { reason: 'required_data_missing' },
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('GPU–Pod 연결 관측 시간');
    expect(html).toContain('7.986');
    expect(html).toContain('산출 불가');
    expect(html).toContain('검증된 GPU 할당 이력이 부족합니다');
    expect(html).not.toContain('<script>');
    expect(html).toContain('<details><summary>원본 결과 보기');
  });
  it('merges query chunks once even when multiple topics reuse the same evidence', () => {
    const quality = {
      observations: [
        { query_id: 'D06', cluster_id: 'cpc-1', tool_status: 'ok', sample_count: 4000 },
        {
          query_id: 'D06',
          cluster_id: 'cpc-1',
          tool_status: 'partial',
          sample_count: 3000,
          reason: 'source_warning',
        },
        { query_id: 'D08', cluster_id: 'cpc-1', tool_status: 'empty', sample_count: 0 },
      ],
    };
    const summary = reportObservations({ topics: [{ quality }, { quality }] });
    expect(summary).toHaveLength(2);
    expect(summary[0]).toMatchObject({
      sample_count: 7000,
      statuses: ['ok', 'partial'],
      reasons: ['source_warning'],
    });
    expect(summary[1]).toMatchObject({ sample_count: 0, statuses: ['empty'] });
  });
});

describe('namespace report usability', () => {
  it('shows valid zero separately from unknown and reports applied grouping before details', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        request={{ group_by: ['namespace'] }}
        value={{
          versions: { criteria: '1.2' },
          quality: { narrative_reason: 'llm_token_budget_exhausted' },
          narrative_status: 'failed',
          topics: [
            {
              topic_id: 'O08',
              status: 'partial',
              quality: { applied_group_by: ['namespace'] },
              metrics: [
                {
                  id: 'O08.observed_namespace_hours.0',
                  target: { cluster_id: 'cpc-1', namespace: 'training' },
                  value: 1,
                  unit: 'GPU-hours',
                },
                {
                  id: 'O08.namespace_activity_valid_hours.0',
                  target: { cluster_id: 'cpc-1', namespace: 'training' },
                  value: 1,
                  unit: 'GPU-hours',
                },
                {
                  id: 'O08.namespace_connected_gpu_util.0',
                  target: { cluster_id: 'cpc-1', namespace: 'training' },
                  value: 0,
                  unit: 'percent',
                },
                {
                  id: 'O08.namespace_connected_gpu_util.1',
                  target: { cluster_id: 'cpc-1', namespace: 'shared' },
                  value: null,
                  unit: 'percent',
                  quality: { reason: 'shared_gpu_attribution_unverified' },
                },
              ],
              recommendations: [
                {
                  eligibility: 'withheld',
                  execution: 'not_performed',
                  text: '작업 목적 확인',
                  reason: 'workload_purpose_unverified',
                  evidence_refs: ['e1'],
                  preconditions: ['workload_exception_review'],
                },
              ],
            },
          ],
        }}
      />,
    ).split('<summary>원본 결과 보기')[0];
    expect(html).toContain('<dt>요청한 집계</dt><dd>Namespace');
    expect(html).toContain('적용된 집계: Namespace');
    expect(html).toContain('0 %');
    expect(html).toContain('산출 불가');
    expect(html).not.toContain('산출 불가 %');
    expect(html).toContain('권고 보류');
    expect(html).toContain('관련 근거 1건 보기');
    expect(html).not.toContain('class="badge badge-blocked">withheld');
    expect(html).toContain('토큰 예산을 초과');
    expect(html.indexOf('Namespace GPU 현황')).toBeLessThan(html.indexOf('주제별 상세 수치'));
  });
  it('does not imply that legacy reports applied the requested namespace calculation', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        request={{ group_by: ['namespace'] }}
        value={{
          versions: { criteria: 'unconfigured' },
          narrative_status: 'failed',
          topics: [
            {
              topic_id: 'O08',
              metrics: [
                {
                  id: 'O08.observed_namespace_hours.0',
                  target: { cluster_id: 'cpc-1', namespace: 'a' },
                  value: 7.986,
                  unit: 'GPU-hours',
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('요청했지만 새 활동률 계산이 적용되지 않았습니다');
    expect(html).toContain('미계산');
    expect(html).toContain('구체적인 실패 이유가 기록되지 않았습니다');
  });
  it('separates collection limits, query failures and empty source responses', () => {
    expect(
      collectionStatus({
        statuses: ['unavailable'],
        reasons: ['budget_exhausted'],
        sample_count: 0,
      }),
    ).toBe('실행 제한으로 미수집');
    expect(
      collectionStatus({
        statuses: ['ok', 'unavailable'],
        reasons: ['budget_exhausted'],
        sample_count: 10,
      }),
    ).toBe('일부 수집 후 제한으로 중단');
    expect(collectionStatus({ statuses: ['unavailable'], reasons: ['query_failed'] })).toBe(
      '조회 실패',
    );
    expect(collectionStatus({ statuses: ['empty'], reasons: [] })).toBe('해당 기간 데이터 없음');
  });
  it('formats readable memory without changing stored values or null semantics', () => {
    const metric = { value: 3 * 1024 * 1024, unit: 'bytes' };
    expect(metricValue(metric)).toBe('3');
    expect(metricUnit(metric)).toBe('MiB');
    expect(metric.value).toBe(3145728);
    expect(metricValue({ value: null, unit: 'bytes' })).toBe('산출 불가');
    expect(metricUnit({ value: 80 * 1024 ** 3, unit: 'bytes' })).toBe('GiB');
  });
  it('uses a review-specific empty message while retaining query error handling', () => {
    const html = renderToStaticMarkup(
      <QueryState
        query={{ isPending: false, isError: false, error: null, refetch: () => {} }}
        empty
        emptyTitle="아직 작성된 검토·조치 기록이 없습니다."
        emptyDescription="검토 의견을 남길 수 있습니다."
      >
        <p>기록</p>
      </QueryState>,
    );
    expect(html).toContain('아직 작성된 검토·조치 기록');
    expect(html).not.toContain('저장된 결과가 없습니다');
  });
});

it('explains elapsed time, cumulative GPU time and topic limitations before details', () => {
  const target = { cluster_id: 'fixture', namespace: 'training' };
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      request={{ group_by: ['namespace'] }}
      value={{
        time_range: { start: '2026-09-30T06:20:00Z', end: '2026-09-30T07:20:00Z' },
        topics: [
          {
            topic_id: 'O08',
            status: 'partial',
            quality: { applied_group_by: ['namespace'] },
            missing_inputs: [
              'unattributed_gpu_observation',
              'observed_mapping_not_exclusive_allocation',
            ],
            metrics: [
              { id: 'O08.namespace_connected_gpu_count.0', target, value: 8, unit: 'physical_gpu' },
              {
                id: 'O08.observed_namespace_hours.0',
                target,
                value: 7.986415555742,
                unit: 'GPU-hours',
              },
              {
                id: 'O08.namespace_activity_valid_hours.0',
                target,
                value: 7.986415555742,
                unit: 'GPU-hours',
              },
              { id: 'O08.namespace_connected_gpu_util.0', target, value: 9.16452, unit: 'percent' },
            ],
          },
        ],
      }}
    />,
  ).split('<details id="report-topic-details">')[0];
  expect(html).toContain('분석 대상 기간');
  expect(html).toContain('· 1시간');
  expect(html).toContain('부분 산출 1개');
  expect(html).toContain('일부 GPU 관측을 Namespace에 연결하지 못했습니다');
  expect(html).toContain('8 대');
  expect(html).toContain('7.986 GPU·시간');
  expect(html).toContain('8대가 각각 1시간');
  expect(html).toContain('9.165 %');
  expect(html).not.toContain('<th>평균에 사용한 시간</th>');
  expect(html).not.toContain('4개 항목 중 4개');
});

it('keeps legacy O08 values in details without advertising namespace analysis for cluster reports', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      request={{ group_by: ['cluster'] }}
      value={{
        topics: [
          {
            topic_id: 'O08',
            status: 'partial',
            metrics: [{ id: 'O08.observed_namespace_hours.0', value: 7.986, unit: 'GPU-hours' }],
          },
        ],
      }}
    />,
  ).split('<summary>원본 결과 보기')[0];
  expect(html).not.toContain('<h3>Namespace GPU 현황</h3>');
  expect(html).not.toContain('새 Namespace 활동률 집계 미적용');
  expect(html).toContain('7.986');
});

it('retains other topic explanations when removing duplicate namespace metric summaries', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      value={{
        topics: [
          {
            topic_id: 'O08',
            quality: { applied_group_by: ['namespace'] },
            metrics: [{ id: 'O08.observed_namespace_hours.0', value: 1, unit: 'GPU-hours' }],
          },
        ],
        narrative: [
          { id: 'other.fact', text: 'Other topic explanation', value_refs: [] },
          {
            id: 'O08.observed_namespace_hours.0.fact',
            text: 'duplicate',
            value_refs: ['O08.observed_namespace_hours.0'],
          },
        ],
      }}
    />,
  ).split('<summary>원본 결과 보기')[0];
  expect(html).toContain('Other topic explanation');
  expect(html).not.toContain('duplicate');
});

it('keeps diagnostics collapsed, separates zero/null and does not invent collection history', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      value={{
        narrative_status: 'failed',
        narrative: [{ title: '분석 범위', text: 'RAW_JSON_PLACEHOLDER' }],
        topics: [
          {
            topic_id: 'O08',
            status: 'partial',
            missing_inputs: ['allocation_contract_missing'],
            metrics: [
              { id: 'O08.namespace_connected_gpu_util.0', value: 0, unit: 'percent' },
              {
                id: 'O08.allocated_gpu_hours',
                value: null,
                quality: { reason: 'allocation_contract_missing' },
              },
            ],
            recommendations: [{ eligibility: 'withheld', reason: 'workload_purpose_unverified' }],
            quality: {
              observations: [
                { query_id: 'D01', cluster_id: 'cpc', tool_status: 'ok', sample_count: 4 },
                { query_id: 'D02', cluster_id: 'cpc', tool_status: 'empty', sample_count: 0 },
                {
                  query_id: 'D06',
                  cluster_id: 'cpc',
                  tool_status: 'unavailable',
                  reason: 'query_failed',
                },
                {
                  query_id: 'D08',
                  cluster_id: 'cpc',
                  tool_status: 'unavailable',
                  reason: 'budget_exhausted',
                  sample_count: 0,
                },
              ],
            },
            evidence_refs: ['e1'],
          },
          { topic_id: 'O11', status: 'blocked' },
        ],
      }}
    />,
  ).split('<summary>원본 결과 보기')[0];
  expect(html).toContain('<details id="report-diagnostics"><summary>분석 진행 상세');
  expect(html).toContain('계산 결과: 1개 산출 · 1개 산출 불가');
  expect(html).toContain('1개 보류');
  expect(html).toContain('조회 기록 없음. 미조회인지 기록 누락인지 확인할 수 없습니다.');
  for (const text of [
    '수집 완료',
    '해당 기간 데이터 없음',
    '조회 실패',
    '실행 제한으로 미수집',
    'allocation_contract_missing',
    '근거 e1',
    '다음 확인',
  ])
    expect(html).toContain(text);
  expect(html.indexOf('분석 요약')).toBeLessThan(html.indexOf('RAW_JSON_PLACEHOLDER'));
  expect(html).toContain('<summary>저장된 보고서 해석');
  expect(collectionStatus({})).toBe('수집 상태 기록 없음');
  expect(collectionNextCheck({ statuses: ['empty'] })).toContain(
    '전체 서버에 데이터가 없다는 뜻은 아닙니다',
  );
});

it('preserves unknown sample counts rather than manufacturing zero', () => {
  const [record] = reportObservations({
    topics: [
      {
        quality: {
          observations: [
            { query_id: 'D08', cluster_id: 'cpc', tool_status: 'ok', sample_count: 2 },
            {
              query_id: 'D08',
              cluster_id: 'cpc',
              tool_status: 'unavailable',
              reason: 'budget_exhausted',
            },
          ],
        },
      },
    ],
  });
  expect(record.sample_count).toBeNull();
  expect(collectionStatus(record)).toBe('실행 제한 · 수집량 기록 없음');
});

it('shows preflight rejection and collected windows without implying sample coverage', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      value={{
        quality: {
          collection: {
            plan_status: 'rejected',
            plan_reason: 'collection_plan_budget_exceeded',
            complete: false,
            planned_calls: 60,
            query_calls: 0,
            query_limit: 48,
            tasks: [
              {
                query_id: 'D06',
                cluster_id: 'cpc-1',
                requested_range: { start: '2026-09-01T00:00:00Z', end: '2026-09-02T00:00:00Z' },
                requested_seconds: 86400,
                incomplete_seconds: 86400,
                data_seconds: 0,
                empty_seconds: 0,
                reserved_calls: 1,
                query_calls: 0,
                ranges: [
                  {
                    time_range: {},
                    status: 'unavailable',
                    reason: 'collection_plan_budget_exceeded',
                    evidence_id: 'e1',
                  },
                ],
              },
            ],
          },
        },
        topics: [],
      }}
    />,
  );
  expect(html).toContain('수집 전 검사에서 중단');
  expect(html).toContain('미완료 24시간');
  expect(html).toContain('빈 응답도 포함');
  expect(html).toContain('근거 보기');
  expect(html).not.toContain('요청한 조회 구간 처리 완료');
});

it('keeps every requested cluster visible and separates zero connections from missing summaries', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      value={{
        scope: {
          clusters: [
            { cluster_id: 'cpc-idle', namespaces: null },
            { cluster_id: 'cpc-missing', namespaces: null },
          ],
        },
        quality: { requested_group_by: ['namespace'] },
        topics: [
          {
            topic_id: 'O08',
            quality: { applied_group_by: ['namespace'] },
            metrics: [
              {
                id: 'O08.cluster_observed_gpu_count.0',
                target: { cluster_id: 'cpc-idle' },
                value: 8,
                unit: 'physical_gpu',
              },
              {
                id: 'O08.cluster_connected_gpu_count.0',
                target: { cluster_id: 'cpc-idle' },
                value: 0,
                unit: 'physical_gpu',
              },
              {
                id: 'O08.cluster_connected_gpu_hours.0',
                target: { cluster_id: 'cpc-idle' },
                value: 0,
                unit: 'GPU-hours',
              },
              {
                id: 'O08.cluster_unlabeled_gpu_count.0',
                target: { cluster_id: 'cpc-idle' },
                value: 8,
                unit: 'physical_gpu',
              },
            ],
          },
        ],
      }}
    />,
  );
  const summary = html.split('클러스터별 GPU 관측 요약')[1].split('연결된 Namespace별 활동')[0];
  expect(summary).toContain('<td>cpc-idle</td><td>8 대</td><td>0 대</td><td>0 GPU·시간</td>');
  expect(summary).toContain('<td>cpc-missing</td><td>미확인</td><td>미확인</td><td>미확인</td>');
  expect(summary).toContain('저장된 클러스터 요약이 없습니다');
  expect(summary).toContain('유휴 여부는 미확인');
});

it('shows report execution duration beside request metadata, separate from the analyzed day', () => {
  const html = renderToStaticMarkup(
    <ReportContent
      onEvidence={() => {}}
      request={{
        status: 'succeeded',
        attempt_no: 1,
        created_at: '2026-10-02T00:00:00Z',
        attempts: [
          { attempt_no: 1, started_at: '2026-10-02T00:01:00Z', ended_at: '2026-10-02T00:06:00Z' },
        ],
      }}
      value={{
        time_range: { start: '2026-09-30T15:00:00Z', end: '2026-10-01T15:00:00Z' },
        topics: [],
      }}
    />,
  );
  expect(html).toContain('<dt>보고서 실행시간</dt>');
  expect(html).toContain('<strong>5분 0초</strong>');
  expect(html).toContain('접수부터 완료까지 6분 0초');
  expect(html).toContain('1일(24시간)');
});

it('shows each topic basis in request details instead of a misleading global cluster label', () => {
  const html = renderToStaticMarkup(
    <DataView
      reportDisplay
      value={{ group_by: ['cluster'], topic_group_by: { O08: ['namespace'], O09: ['cluster'] } }}
    />,
  );
  expect(html).toContain('소주제별 표시 기준');
  expect(html).toContain('클러스터·Namespace별 연결 관측');
  expect(html).toContain('선택 범위 전체의 관측 GPU 에너지 합계');
  expect(html).not.toContain('<dt>집계 기준</dt>');
});
