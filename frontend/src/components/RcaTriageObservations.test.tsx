import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaTriageObservations } from './RcaTriageObservations';
import { RcaNarrative } from './RcaNarrative';

const metric = {
  name: 'NVLink RX',
  unit: 'bytes/s',
  min: 0,
  max: 0,
  last_value: 0,
  first: '2026-10-21T06:00:00Z',
  last: '2026-10-21T06:10:00Z',
  samples: 13,
};
const result = {
  quality: {
    report: { presentation: 'incident-first/2' },
    triage_observations: {
      schema: 'rca-triage-observations/1',
      target: { node: 'dgx02' },
      logs: [{ code: 'sxid:11001', first: metric.first, last: metric.last, reports: 6 }],
      metrics: [
        { ...metric, gpu_uuid: 'GPU-A' },
        { ...metric, gpu_uuid: 'GPU-B' },
        { ...metric, gpu_uuid: 'GPU-C', max: 1 },
      ],
    },
  },
  narrative: [
    { id: 'comparison', title: '비교 상세', text: '저장된 비교 원문' },
    { id: 'action', title: '권고 조치', text: '진단 자료 보존' },
    { id: 'cause', title: '분석 결과', text: '기록에 근거한 결론' },
  ],
};
it('groups identical summaries without hiding different measurements or GPU identities', () => {
  const html = renderToStaticMarkup(<RcaTriageObservations result={result} />);
  expect(html.match(/NVLink RX/g)).toHaveLength(2);
  expect(html).toContain('GPU 2개');
  for (const gpu of ['GPU-A', 'GPU-B', 'GPU-C']) expect(html).toContain(gpu);
});
it('shows guidance, observations, analysis and references in operator order', () => {
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(html.indexOf('2. 대응 순서')).toBeLessThan(html.indexOf('3. 관련 로그·메트릭'));
  expect(html.indexOf('진단 자료 보존')).toBeLessThan(html.indexOf('사건 로그와 관련 지표'));
  expect(html.indexOf('진단 자료 보존')).toBeLessThan(html.indexOf('기록에 근거한 결론'));
  expect(html.indexOf('4. 분석 및 해석')).toBeLessThan(html.indexOf('6. 참고 자료'));
  expect(html).not.toContain('분석 처리:');
  expect(html.indexOf('사건 로그와 관련 지표')).toBeLessThan(html.indexOf('6. 참고 자료'));
  expect(html).not.toContain('<summary>5. 조사');
  expect(html).toContain('저장된 비교 원문');
  expect(JSON.stringify(result)).toBe(before);
});

it('renders enum codes without treating them as numeric ranges or health', () => {
  const value = {
    quality: {
      triage_observations: {
        schema: 'rca-triage-observations/1',
        metrics: [{ ...metric, name: 'FM', unit: 'enum' }],
      },
    },
  };
  const html = renderToStaticMarkup(<RcaTriageObservations result={value} />);
  expect(html).toContain('상태 코드 0 유지');
  expect(html).not.toContain('최소');
  expect(html).not.toContain('마지막 값');
  expect(html).not.toContain('정상');
});

it('keeps analytical explanation visible and only folds tagged raw data', () => {
  const value = {
    ...result,
    quality: {
      ...result.quality,
      report: {
        ...result.quality.report,
        source_items: [
          { section: 'comparison', text: '원시 측정 목록', fixed: true, detail_only: true },
        ],
      },
    },
    narrative: [
      { id: 'comparison', title: '자료 비교', text: '사건 전후의 변화 설명\n\n원시 측정 목록' },
    ],
  };
  const html = renderToStaticMarkup(<RcaNarrative result={value} />);
  expect(html).toContain('사건 전후의 변화 설명</p>');
  expect(html.indexOf('사건 전후의 변화 설명')).toBeLessThan(
    html.indexOf('<summary>수집 원문·처리 상세</summary>'),
  );
  expect(html).toContain('<summary>수집 원문·처리 상세</summary>');
  expect(html.match(/원시 측정 목록/g)).toHaveLength(1);
});

it('preserves actual UUIDs, event time and pre-event measurement limits in Korean', () => {
  const gpu = 'GPU-11111111-2222-3333-4444-555555555555';
  const value = {
    quality: {
      report: {
        presentation: 'incident-first/2',
        source_items: [
          {
            section: 'cause',
            text: `${gpu}의 관측 전력은 사건 이전 구간에 해당합니다.`,
            evidence_refs: ['source'],
          },
        ],
      },
      triage_observations: {
        schema: 'rca-triage-observations/1',
        target: { node: 'test-node' },
        event_boundary: '2026-01-02T01:10:12Z',
        logs: [
          {
            code: 'sxid:11001',
            device: 'PCI:0000:ca:00.0',
            event_times: ['2026-01-02T01:10:12Z'],
            first: '2026-01-02T01:10:25Z',
            last: '2026-01-02T01:11:25Z',
            reports: 2,
          },
        ],
        metrics: [
          {
            ...metric,
            gpu_uuid: gpu,
            unit: 'percent',
            first: '2026-01-02T00:45:25Z',
            last: '2026-01-02T01:04:25Z',
          },
        ],
      },
    },
    narrative: [],
  };
  const html = renderToStaticMarkup(<RcaNarrative result={value} />);
  expect(html).toContain(gpu);
  expect(html).not.toContain('GPU 1 (보고서 표기)');
  expect(html).toContain('2026. 01. 02. 10:10:12 KST');
  expect(html).toContain('사건 발생 이전의 측정 기록');
  expect(html).toContain('0 %');
  expect(html).not.toContain('0 percent');
});

it('keeps switch PCI separate from GPU inventory and links previous RCA', () => {
  const value = {
    quality: {
      report: { presentation: 'incident-first/2' },
      triage_observations: {
        schema: 'rca-triage-observations/1',
        switch_pci: [{ reported_pci: ['0000:ca:00.0'], observed_pci: [], status: 'empty' }],
      },
      host_incident_history: {
        schema: 'rca-host-history/1',
        period: { start: '2026-01-01T00:00:00Z', end: '2026-01-03T00:00:00Z' },
        complete: true,
        rows: [
          {
            incident_id: 'incident-1',
            occurred_at: '2026-01-02T00:00:00Z',
            codes: ['sxid:11001'],
            device: 'NVSwitch PCI:0000:ca:00.0',
            prior_rca: { job_id: 'prior-job', result_status: 'partial' },
          },
        ],
      },
    },
    narrative: [],
  };
  const html = renderToStaticMarkup(<RcaNarrative result={value} />);
  expect(html).toContain('NVSwitch PCI:0000:ca:00.0');
  expect(html).toContain('해당 구간에 일치하는 시계열 없음');
  expect(html).toContain('/analyses/prior-job#final-report');
  expect(html).toContain('알림 기준 시각');
  expect(html).toContain('일부 자료로 작성된 보고서');
});

it('takes fabric checks from the published Runbook and avoids a duplicate escalation step', () => {
  const guidance = (text: string) => ({
    report_applicability: 'matched',
    guidance: {
      meaning: 'SXID 11001 의미입니다.',
      next_checks: [{ title: '패브릭 상태 확인', text }],
      references: [],
    },
  });
  const report = (text: string) =>
    renderToStaticMarkup(
      <RcaNarrative
        result={{
          ...result,
          quality: { ...result.quality, runbook_guidance: [guidance(text)] },
        }}
      />,
    );
  const withEscalation = report(
    'nvidia-smi nvlink -s로 확인합니다. dcgmi diag -r 3으로 진단합니다.',
  );
  expect(withEscalation).toContain('패브릭 상태 확인');
  expect(withEscalation).not.toContain('조치 후 확인·에스컬레이션');
  expect(report('nvidia-smi nvlink -s로 확인합니다.')).toContain('조치 후 확인·에스컬레이션');
});

it('explains a missing AI narrative, operator-written checklist rows and pods by GPU', () => {
  const gpu = 'GPU-11111111-2222-3333-4444-555555555555';
  const span = { first: '2026-10-22T07:30:13Z', last: '2026-10-22T07:56:43Z' };
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{
        missing_inputs: ['synthesis_failed'],
        quality: {
          analysis: { synthesis: { error_code: 'llm_http_error', http_status: 500 } },
          runbook_guidance: [{ guidance: { meaning: 'XID 79 의미입니다.', next_checks: [] } }],
          triage_observations: {
            schema: 'rca-triage-observations/1',
            target: { node: 'dgx01', title: `XID 79 detected on GPU PCI:0000:bd:00 UUID:${gpu}` },
            event_boundary: '2026-10-22T07:55:24Z',
            logs: [{ code: 'xid:79', device: 'PCI:0000:bd:00', ...span, reports: 2 }],
            gpus: [
              { gpu_uuid: gpu, gpu_index: '7', driver: '580.173.02' },
              { gpu_uuid: 'GPU-B', gpu_index: '4' },
              { gpu_uuid: 'GPU-C', gpu_index: '0' },
            ],
            workloads: [
              { gpu_uuid: gpu, namespace: 'ns', pod: 'worker-a', ...span },
              { gpu_uuid: 'GPU-B', namespace: 'ns', pod: 'worker-a', ...span },
              { gpu_uuid: 'GPU-C', namespace: 'ns', pod: 'worker-c', ...span },
            ],
          },
        },
      }}
    />,
  );
  expect(html).toContain('AI 해석 실패 · HTTP 500');
  expect(html).toContain('AI가 쓰는 해석 문장만 빠졌습니다 — LLM 호출 실패 (HTTP 500)');
  expect(html).not.toContain('표·판정은 코드 산출');
  expect(html).toContain('✍ 운영자 작성');
  expect(html).toContain('이 보고서는 조치를 수행하지 않습니다');
  expect(html).toContain('✅ 드라이버 580.173.02 (DCGM 라벨)');
  expect(html).toContain('ns / worker-a (GPU 4·7번 · 2개 함께 사용)');
  expect(html).toContain('ns / worker-c (GPU 0번)');
});

it('keeps the six-section frame when a result has no triage observations', () => {
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{
        runbook_revisions: [
          { knowledge_key: 'RB-SXID-11001', revision: 13 },
          { knowledge_key: 'RB-GENERAL-GPU-NODE', revision: 3 },
        ],
        quality: { analysis: { workflow: 'single_collection' } },
        narrative: [{ id: 'action', title: '권고 조치', text: '진단 자료 보존' }],
      }}
    />,
  );
  for (const heading of [
    '1. 한눈에 보기',
    '2. 대응 순서',
    '3. 관련 로그·메트릭',
    '4. 분석 및 해석',
    '5. 이전 사건 이력',
    '6. 참고 자료',
  ])
    expect(html).toContain(heading);
  expect(html).toContain('(사용 Runbook: RB-SXID-11001 rev 13)');
  expect(html).not.toContain('RB-GENERAL-GPU-NODE rev');
});
