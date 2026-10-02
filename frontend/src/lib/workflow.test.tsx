import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { WorkflowGuide } from '../components/WorkflowGuide';
import { ReportContent } from '../components/ReportContent';
import {
  rcaSteps,
  reportScopeClusters,
  reportTitle,
  reportTopics,
  reportSteps,
  workflowValues,
} from './workflow';
import { apiRequest, apiTraceSnapshot, clearApiTrace } from './api';

describe('mode-independent published data and developer guides', () => {
  it('identifies report topics and scope without guessing missing metadata', () => {
    expect(reportTopics({ topic_ids: ['O01', 'O11', 'future-topic'] })).toBe(
      '장비·Node 변화 · 관측 품질 · future-topic',
    );
    expect(reportTitle({ topic_ids: ['O01', 'O11'] })).toBe('GPU 운영 보고서 · 2개 주제');
    expect(reportTitle({ topic_ids: ['O08'], group_by: ['namespace'] })).toBe(
      'Namespace별 GPU 사용 분석',
    );
    expect(reportTitle({})).toBe('분석 주제 미확인');
    expect(reportScopeClusters({})).toEqual([]);
    expect(
      reportScopeClusters({
        scope: {
          clusters: [
            { cluster_id: 'cpc-1', namespaces: null },
            { cluster_id: 'cpc-2', namespaces: ['a', 'b'] },
            { cluster_id: 'cpc-3' },
            { cluster_id: 'cpc-4', namespaces: [] },
          ],
        },
      }),
    ).toEqual([
      { cluster: 'cpc-1', namespaces: '전체 Namespace' },
      { cluster: 'cpc-2', namespaces: 'a, b' },
      { cluster: 'cpc-3', namespaces: 'Namespace 범위 미확인' },
      { cluster: 'cpc-4', namespaces: '선택된 Namespace 없음' },
    ]);
  });
  it.each([
    ['2026-09-30T15:00:00Z', '2026-10-01T15:00:00Z', '2026. 10. 01.'],
    ['2026-09-24T15:00:00Z', '2026-10-01T15:00:00Z', '2026. 09. 25. ~ 2026. 10. 01.'],
    ['2026-10-01T03:00:00Z', '2026-10-01T05:00:00Z', '2026. 10. 01.'],
    ['2026-12-31T14:00:00Z', '2026-12-31T16:00:00Z', '2026. 12. 31. ~ 2027. 01. 01.'],
    ['invalid', '2026-10-01T05:00:00Z', ''],
    ['2026-10-02T05:00:00Z', '2026-10-01T05:00:00Z', ''],
  ])('titles reports using their analyzed dates: %s to %s', (start, end, dates) => {
    expect(
      reportTitle({
        topic_ids: ['O08'],
        group_by: ['namespace'],
        time_range: { start, end },
        created_at: '2027-02-01T00:00:00Z',
      }),
    ).toBe(`${dates ? dates + ' · ' : ''}Namespace별 GPU 사용 분석`);
  });
  it('records bounded HTTP metadata without query values or request/response bodies', async () => {
    clearApiTrace();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ request_id: 'req-1', secret: 'response-secret' }), {
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    );
    try {
      for (let i = 0; i < 51; i++)
        await apiRequest('/reports?scope=private-scope', {
          method: 'POST',
          body: { secret: 'request-secret' },
          idempotencyKey: 'private-key',
        });
      expect(apiTraceSnapshot()).toHaveLength(50);
      expect(apiTraceSnapshot()[0]).toMatchObject({
        method: 'POST',
        path: '/reports',
        status: 200,
        requestId: 'req-1',
      });
      expect(JSON.stringify(apiTraceSnapshot())).not.toMatch(/secret|private/);
    } finally {
      vi.unstubAllGlobals();
      clearApiTrace();
    }
  });
  it('does not expose a candidate when the job has no published reference', () => {
    const step = reportSteps.find((s) => s.title === '주제별 결정적 계산')!;
    expect(
      workflowValues(step, { result: { topics: [{ secret: 'candidate' }] } }).topics,
    ).toBeNull();
    expect(
      workflowValues(step, {
        result_ref: 'published',
        result: { versions: { criteria: '1.2' }, topics: [] },
      }),
    ).toMatchObject({ versions: { criteria: '1.2' }, topics: [] });
  });
  it('explains actual report and RCA paths without asserting missing stages succeeded', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <WorkflowGuide
          job={{ id: 'job-1', kind: 'report', status: 'queued', stage: null, result_ref: null }}
        />
      </MemoryRouter>,
    );
    expect(html).toContain('미공개');
    expect(html).toContain('정상 판정 아님');
    expect(html).toContain('DB 스냅샷');
    expect(html).toContain('실시간 실행 추적이 아님');
    expect(rcaSteps.some((s) => s.inspect.includes('quality.analysis'))).toBe(true);
    expect(reportSteps.some((s) => s.missing.includes('현재 문서상 목표'))).toBe(true);
  });
  it('preserves zero, unknown values, valid-time denominators and withheld recommendations', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        value={{
          versions: { criteria: '1.2' },
          narrative_status: 'failed',
          topics: [
            {
              topic_id: 'O08',
              status: 'partial',
              quality: {
                requested_group_by: ['namespace'],
                applied_group_by: ['namespace'],
                interpretation: 'Namespace 실사용률이 아닙니다.',
              },
              metrics: [
                {
                  id: 'O08.namespace_connected_gpu_util.0',
                  value: 0,
                  unit: 'percent',
                  denominator: { value: 3600, unit: 'GPU-seconds' },
                  quality: { excluded_reasons: ['conflicting_gpu_activity'] },
                },
                {
                  id: 'O08.namespace_activity_valid_hours.0',
                  value: null,
                  quality: { reason: 'gpu_activity_missing' },
                },
              ],
              recommendations: [
                {
                  id: 'rec',
                  text: '할당 점검',
                  eligibility: 'withheld',
                  execution: 'not_performed',
                  reason: 'allocation_contract_missing',
                  value_refs: ['not-found'],
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('연결 GPU 평균 활동률');
    expect(html).toContain('>0<');
    expect(html).toContain('산출 불가');
    expect(html).toContain('3600');
    expect(html).toContain('활동값이 충돌');
    expect(html).toContain('권고 보류');
    expect(html).toContain('조치 미수행');
    expect(html).toContain('수치 참조 미확인');
    expect(html).toContain('AI 설명을 생성하지 못했습니다');
  });
});
