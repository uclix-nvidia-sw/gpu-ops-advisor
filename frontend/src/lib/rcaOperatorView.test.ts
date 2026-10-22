import { expect, it } from 'vitest';
import { fullPci, operatorView, sentences } from './rcaOperatorView';

const gpu = 'GPU-81ec1404-9d04-9bdf-0bdc-c852d61759a9';
const other = 'GPU-7608a7b1-ec78-22f7-d932-8c629aed27b1';
const before = (max: number, last = '2026-10-22T03:27:24Z') => ({
  first: '2026-10-22T03:00:24Z',
  last,
  min: 0,
  max,
  last_value: 0,
  samples: 21,
});
// Shape mirrors a stored XID 79 single-collection result (values are synthetic).
const result = {
  result_status: 'partial',
  missing_inputs: ['event_not_found', 'synthesis_failed'],
  device_observations: [{ gpu_candidates: [{ gpu_uuid: gpu, bus_id: '0000:4e:00.0' }] }],
  quality: {
    triage_observations: {
      schema: 'rca-triage-observations/1',
      alert_time: '2026-10-22T03:28:10Z',
      event_boundary: '2026-10-22T03:28:10Z',
      period: { start: '2026-10-22T02:58:47Z', end: '2026-10-22T03:28:47Z' },
      metric_scope: 'reported_gpu',
      target: {
        node: 'dgx01',
        cluster_id: 'cpc-1',
        title: `XID 79 GPU has fallen off the bus detected on GPU PCI:0000:4e:00 UUID:${gpu}`,
      },
      logs: [
        {
          code: 'xid:79',
          device: 'PCI:0000:4e:00',
          event_times: [],
          first: '2026-10-22T03:27:24Z',
          last: '2026-10-22T03:28:24Z',
          reports: 2,
        },
      ],
      metrics: [
        {
          name: 'GPU 전력',
          unit: 'watts',
          kind: 'gauge',
          gpu_uuid: gpu,
          last: '2026-10-22T03:27:24Z',
          max_sample_gap_seconds: 300,
          incident_windows: { before: before(262), at_or_after: null },
        },
        {
          name: 'GPU 사용률',
          query_id: 'D02',
          unit: 'percent',
          kind: 'gauge',
          gpu_uuid: gpu,
          last: '2026-10-22T03:28:43Z',
          max_sample_gap_seconds: 15,
          incident_windows: {
            before: before(100),
            at_or_after: { ...before(0, '2026-10-22T03:28:43Z'), samples: 3 },
          },
        },
      ],
    },
    host_incident_history: {
      schema: 'rca-host-history/1',
      period: { start: '2026-10-08T03:28:47Z', end: '2026-10-22T03:28:47Z' },
      rows: [
        {
          incident_id: 'a',
          current: true,
          codes: ['xid:79'],
          gpu_uuid: gpu,
          occurred_at: '2026-10-22T03:28:10Z',
        },
        { incident_id: 'b', codes: ['xid:79'], gpu_uuid: gpu, occurred_at: '2026-10-22T01:11:10Z' },
        {
          incident_id: 'c',
          codes: ['xid:79'],
          gpu_uuid: other,
          occurred_at: '2026-10-21T01:11:10Z',
        },
        {
          incident_id: 'd',
          codes: ['sxid:11001'],
          device: 'NVSwitch PCI:0000:c7:00.0',
          occurred_at: '2026-10-21T02:00:00Z',
        },
      ],
    },
  },
};

it('answers the operator questions from collected evidence only', () => {
  const v = operatorView(result)!;
  const [identity, timing, telemetry, repeat, gaps] = v.findings;
  expect(identity.tone).toBe('ok');
  expect(identity.points.join()).toContain(`PCI 0000:4e:00.0 = ${gpu}`);
  expect(timing.tone).toBe('alert');
  expect(timing.points[0]).toContain('정상→오류 전환도 없습니다');
  expect(telemetry.tone).toBe('warn');
  expect(v.metrics.find((m) => m.name === 'GPU 사용률')!.short).toContain('작업이 멈췄습니다');
  // 83 s of silence is within a 300 s collection gap, so absence is not called an outage.
  expect(v.metrics.find((m) => m.name === 'GPU 전력')!.tag).toBe('판단 보류');
  expect(repeat.tone).toBe('alert');
  expect(repeat.points.join('\n')).toContain('(추정) 여러 GPU에서 같은 오류');
  expect(repeat.points.join('\n')).toContain('XID)와 NVSwitch 오류(SXID)');
  expect(v.devices[0]).toMatchObject({ count: 2, current: true });
  expect(gaps.points.join()).toContain('AI 해석 문장이 없습니다');
  // '정상 보고' names Fleet's Healthy report; the report never judges the device healthy.
  expect(JSON.stringify(v.findings)).not.toMatch(
    /정상(입니다|으로 판단|으로 회복|으로 보입니다| 상태)/,
  );
});

it('returns null for results without triage observations', () => {
  expect(operatorView({ quality: {} })).toBeNull();
});

it('keeps full PCI addresses and splits Korean guidance into lines', () => {
  expect(fullPci('PCI:00000000:4E:00.0')).toBe('0000:4e:00.0');
  expect(sentences('보존합니다. 재시작은 상태를 바꿉니다. CUDA 12.7 기준')).toHaveLength(3);
});

it('flags uncorrectable ECC growth and treats bitmasks as codes', () => {
  const view = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        metrics: [
          {
            name: 'DBE',
            unit: 'count',
            kind: 'counter',
            query_id: 'D40',
            gpu_uuid: gpu,
            last: '2026-10-22T03:28:40Z',
            incident_windows: {
              before: before(0),
              at_or_after: { ...before(2, '2026-10-22T03:28:40Z'), min: 2 },
            },
          },
          {
            name: '클록 제한 사유',
            unit: 'bitmask',
            kind: 'enum',
            query_id: 'D45',
            gpu_uuid: gpu,
            last: '2026-10-22T03:28:40Z',
            incident_windows: {
              before: { ...before(4), min: 4 },
              at_or_after: { ...before(4, '2026-10-22T03:28:40Z'), min: 4 },
            },
          },
        ],
      },
    },
  })!;
  expect(view.metrics[0].tone).toBe('alert');
  expect(view.metrics[1].reading).toContain('상태 코드 4 유지');
  expect(view.findings[2].tone).toBe('alert');
});

it('bounds the onset by state reports and names workloads on the GPU', () => {
  const view = operatorView({
    ...result,
    quality: {
      ...result.quality,
      triage_observations: {
        ...result.quality.triage_observations,
        onset: {
          last_healthy_at: '2026-10-22T03:26:24Z',
          first_unhealthy_at: '2026-10-22T03:27:24Z',
        },
        gpus: [
          {
            gpu_uuid: gpu,
            pci_bus_id: '00000000:4E:00.0',
            model: 'NVIDIA A100',
            driver: '580.1',
            gpu_index: '3',
          },
        ],
        workloads: [
          {
            gpu_uuid: gpu,
            namespace: 'ns',
            pod: 'worker-b',
            first: '2026-10-22T03:20:00Z',
            last: '2026-10-22T03:28:40Z',
          },
        ],
      },
    },
  })!;
  expect(view.onsetText).toContain('사이에 시작');
  expect(view.findings[1].points[0]).toContain('상태 보고로');
  expect(view.workloads).toMatchObject([{ name: 'ns / worker-b', atIncident: true }]);
  expect([view.gpuModel, view.driver, view.gpuIndex]).toEqual(['NVIDIA A100', '580.1', '3']);
  expect(view.findings[4].points.join()).not.toContain('드라이버 버전');
  expect(view.metrics[0].gpus[0]).toBe(`PCI 0000:4e:00.0 · ${gpu}`);
});
