import { expect, it } from 'vitest';
import {
  aiFailure,
  fullPci,
  operatorView,
  plainReason,
  sentences,
  valueText,
} from './rcaOperatorView';

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
            before: { ...before(100), last_value: 100 },
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
  expect(timing.tone).toBe('unknown');
  expect(timing.verdict).toContain('마지막 오류 기록:');
  expect(timing.verdict).toContain('현재 지속·복구 여부를 판단할 수 없습니다');
  expect(timing.points[0]).toContain('정상→오류 전환도 없습니다');
  expect(telemetry.tone).toBe('warn');
  expect(v.metrics.find((m) => m.name === 'GPU 사용률')!.short).toContain('사건 뒤 0 % 관측');
  // 83 s of silence is within a 300 s collection gap, so absence is not called an outage.
  expect(v.metrics.find((m) => m.name === 'GPU 전력')!.tag).toBe('사건 전 표본');
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

it('does not infer persistence or recovery from the last log proximity or missing timestamps', () => {
  for (const last of ['2026-10-22T03:28:46Z', '2026-10-22T02:59:00Z', '', 'invalid']) {
    const v = operatorView({
      ...result,
      quality: {
        triage_observations: {
          ...result.quality.triage_observations,
          logs: [{ code: 'xid:79', first: last, last, reports: 1 }],
        },
      },
    })!;
    expect(v).not.toHaveProperty('ongoing');
    const timing = v.findings.find((f) => f.key === 'timing')!;
    expect(timing.tone).toBe('unknown');
    expect(timing.verdict).toContain('판단할 수 없습니다');
    expect(timing.verdict).toContain(
      last && last !== 'invalid' ? '마지막 오류 기록:' : '시각을 확인하지 못했습니다',
    );
  }
});

it('names supporting metrics the worker could not fetch without judging from them', () => {
  const v = operatorView({
    ...result,
    quality: {
      ...result.quality,
      optional_unavailable: [{ query_id: 'D11', name: 'GPU 전력' }],
    },
  })!;
  const gaps = v.findings[4].points.join('\n');
  expect(gaps).toContain('추가 대조 자료: GPU 전력');
  expect(gaps).toContain('판단 근거에 포함되지 않았습니다');
  expect(gaps).not.toContain('D11');
});

it('scopes the report to the alert code and device; other node errors stay context', () => {
  // Shape of a stored SXID 11001 result whose window also caught a GPU XID 79 (synthetic).
  const view = (title: string) =>
    operatorView({
      quality: {
        triage_observations: {
          schema: 'rca-triage-observations/1',
          target: { node: 'dgx02', title },
          period: { start: '2026-10-23T04:55:16Z', end: '2026-10-23T05:25:16Z' },
          gpus: [{ gpu_index: '5', gpu_uuid: gpu, pci_bus_id: '0000:90:00.0' }],
          logs: [
            {
              code: 'xid:79',
              device: 'PCI:0000:90:00',
              event_times: ['2026-10-23T05:03:00Z'],
              first: '2026-10-23T05:03:00Z',
              last: '2026-10-23T05:17:25Z',
              reports: 16,
              message: 'NVRM: Xid (PCI:0000:90:00): 79, GPU has fallen off the bus',
            },
            {
              code: 'sxid:11001',
              device: 'PCI:0000:c4:00.0',
              event_times: ['2026-10-23T05:23:44Z'],
              first: '2026-10-23T05:23:44Z',
              last: '2026-10-23T05:24:25Z',
              reports: 2,
              message: 'SXID 11001(ingress invalid command) detected on PCI:0000:c4:00.0',
            },
          ],
        },
      },
    })!;
  const v = view('SXID 11001(ingress invalid command) detected on PCI:0000:c4:00.0');
  expect(v.codes).toEqual(['SXID:11001']);
  expect([v.eventTime, v.reports]).toEqual(['2026-10-23T05:23:44Z', 2]);
  expect(v.message).toContain('SXID 11001');
  expect(v.findings[0].tone).toBe('ok');
  expect(v.findings[0].points[1]).toBe(
    '오류 로그 장치: PCI:0000:c4:00.0 → 알림과 일치 (같은 노드의 GPU 5 (PCI 0000:90:00) XID:79는 대조에서 제외)',
  );
  expect(v.otherNotes[0]).toContain('XID:79 · GPU 5 (PCI 0000:90:00)');
  expect(v.otherNotes[0]).toContain('16건 보고 — 이 알림 오류 21분 전, 이 보고서의 대상 아님');
  expect(v.timeline.map((i) => i.label)).toContain(
    '참고: 같은 노드 XID:79 · GPU 5 (PCI 0000:90:00) (이 보고서 대상 아님)',
  );
  // Same code on another device is still the alert's error, reported as a mismatch.
  const moved = view('SXID 11001(ingress invalid command) detected on PCI:0000:c7:00.0');
  expect(moved.findings[0].tone).toBe('warn');
  expect(moved.reports).toBe(2);
});

it('distinguishes unregistered collection, missing server binding and a completed empty query', () => {
  const source = {
    ...result,
    quality: {
      ...result.quality,
      collection_checks: [
        { title: 'Fabric Manager 원본', status: 'connection_required', query_ids: [] },
        {
          title: '보조 로그 문맥',
          status: 'connection_required',
          query_ids: ['D13'],
          reasons: ['binding_scope_unavailable'],
        },
        { title: '조회 자료', status: 'empty', query_ids: ['D09'] },
      ],
      optional_unavailable: [{ query_id: 'D13', name: '업무 영향·성과' }],
    },
  };
  const original = JSON.stringify(source);
  const points = operatorView(source)!.findings[4].points.join('\n');
  expect(points).toContain('조회가 등록되어 있지 않습니다');
  expect(points).toContain('이번 서버·클러스터에 사용할 조회 연결이 없어 실행되지 않았습니다');
  expect(points).toContain('조회는 완료했으며 해당 대상·기간의 자료는 0건');
  expect(points).not.toContain('업무 영향·성과');
  expect(JSON.stringify(source)).toBe(original);
});

it('returns null for results without triage observations', () => {
  expect(operatorView({ quality: {} })).toBeNull();
});

it('keeps full PCI addresses and splits Korean guidance into lines', () => {
  expect(fullPci('PCI:00000000:4E:00.0')).toBe('0000:4e:00.0');
  expect(sentences('보존합니다. 재시작은 상태를 바꿉니다. CUDA 12.7 기준')).toHaveLength(3);
  expect(sentences('오류입니다(GPU has fallen off the bus). 작업은 멈춥니다.')).toEqual([
    '오류입니다(GPU has fallen off the bus).',
    '작업은 멈춥니다.',
  ]);
  // A parenthesis that does not close a Korean sentence stays inside it.
  expect(sentences('XID 79(PCIe). 확인합니다.')).toHaveLength(1);
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

it('does not blame the error for a GPU that was already idle before it', () => {
  const metrics = result.quality.triage_observations.metrics.map((m) =>
    m.query_id === 'D02'
      ? { ...m, incident_windows: { ...m.incident_windows, before: before(100) } }
      : m,
  );
  const v = operatorView({
    ...result,
    quality: {
      ...result.quality,
      triage_observations: { ...result.quality.triage_observations, metrics },
    },
  })!;
  const util = v.metrics.find((m) => m.name === 'GPU 사용률')!;
  expect([util.tag, util.tone]).toEqual(['사건 전부터 0', 'unknown']);
  expect(v.findings[2].verdict).toContain(
    '사건 전부터 0: GPU 사용률 — 사건 전에 이미 0이 관측됐습니다 (직전 값 0 %',
  );
  expect(v.findings[2].verdict).not.toContain('작업이 멈췄습니다');
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
          { gpu_uuid: other, gpu_index: '7' },
          { gpu_uuid: 'GPU-C', gpu_index: '0' },
        ],
        workloads: [
          {
            gpu_uuid: gpu,
            namespace: 'ns',
            pod: 'worker-b',
            first: '2026-10-22T03:20:00Z',
            last: '2026-10-22T03:28:40Z',
          },
          // The same pod also holds GPU 7; worker-c runs alone on GPU 0.
          {
            gpu_uuid: other,
            namespace: 'ns',
            pod: 'worker-b',
            first: '2026-10-22T03:20:00Z',
            last: '2026-10-22T03:28:40Z',
          },
          {
            gpu_uuid: 'GPU-C',
            namespace: 'ns',
            pod: 'worker-c',
            first: '2026-10-22T03:00:00Z',
            last: '2026-10-22T03:28:40Z',
          },
        ],
      },
    },
  })!;
  expect(view.onsetText).toContain('사이에 시작');
  expect(view.findings[1].points[0]).toContain('상태 보고로');
  expect(view.workloads).toMatchObject([
    { name: 'ns / worker-b', atIncident: true, gpus: 'GPU 3·7번', gpuCount: 2 },
  ]);
  expect(view.neighbours).toMatchObject([{ name: 'ns / worker-c', gpus: 'GPU 0번' }]);
  expect([view.gpuModel, view.driver, view.gpuIndex]).toEqual(['NVIDIA A100', '580.1', '3']);
  expect(view.findings[4].points.join()).not.toContain('드라이버 버전');
  expect(view.metrics[0].gpus[0]).toBe(`PCI 0000:4e:00.0 · ${gpu}`);
});

it('names GPUs that share a verdict instead of listing every series', () => {
  const nvlink = (name: string, query: string, uuid: string, last: number, after: number) => ({
    name,
    query_id: query,
    unit: 'bytes_per_second',
    kind: 'gauge',
    gpu_uuid: uuid,
    max_sample_gap_seconds: 60,
    incident_windows: {
      before: { ...before(Math.max(last, 273775903)), last_value: last },
      at_or_after: {
        ...before(after, '2026-10-22T03:28:40Z'),
        min: after,
        last_value: after,
        samples: 1,
      },
    },
  });
  const gpus = [
    ['GPU-7', '7', 272737481, 0],
    ['GPU-5', '5', 273064763, 4024947],
    ['GPU-4', '4', 279084193, 262456706],
    ['GPU-0', '0', 0, 0],
  ] as const;
  const v = operatorView({
    ...result,
    quality: {
      ...result.quality,
      triage_observations: {
        ...result.quality.triage_observations,
        metric_scope: 'node_gpu_context',
        gpus: gpus.map(([uuid, index]) => ({ gpu_uuid: uuid, gpu_index: index })),
        metrics: gpus.flatMap(([uuid, , last, after]) => [
          nvlink('NVLink 수신량', 'D33', uuid, last, after),
          nvlink('NVLink 송신량', 'D34', uuid, last, after),
          {
            name: 'Fabric Manager 상태',
            query_id: 'D47',
            unit: 'enum',
            kind: 'enum',
            gpu_uuid: uuid,
            incident_windows: { before: before(0), at_or_after: { ...before(0), samples: 1 } },
          },
        ]),
      },
    },
  })!;
  expect(v.gpuRows.map((r) => [r.gpus, r.tag])).toEqual([
    ['GPU 7번', '0 관측'],
    ['GPU 5번', '급감'],
    ['GPU 4번', '유지'],
    ['GPU 0번', '사건 전부터 0'],
  ]);
  expect(v.gpuRows[0].lines).toContain('NVLink 수신량·송신량: 272.7 MB/s → 0 B/s');
  // D47 codes are read with the DCGM Fabric Manager status names.
  expect(v.gpuCommon).toEqual([
    'Fabric Manager 상태: 조회 값 0 — 해당 GPU는 이 지표로 FM 상태를 제공하지 않음. FM 서비스 실행 여부·오류 내용은 서비스 로그로 확인',
  ]);
  expect(v.findings[2].verdict).toBe(
    '사건 직후 GPU 7번 NVLink 수신량·송신량 0 관측, GPU 5번 NVLink 수신량·송신량 급감. 사건 전부터 0: GPU 0번 NVLink 수신량·송신량.',
  );
  expect(v.findings[2].points).toContain(
    'FM 상태 제공 대상 아님: GPU 4개 모두 Fabric Manager 상태 — 조회 값 0 — 해당 GPU는 이 지표로 FM 상태를 제공하지 않음. FM 서비스 실행 여부·오류 내용은 서비스 로그로 확인',
  );
  expect(v.findings[2].points.join('\n')).not.toMatch(/\d{7,} B\/s/);
  // Fleet NVLink series carry no pod labels: the report must not claim "no pods".
  expect(v.podsKnown).toBe(false);
});

it('names the gateway error class and limit recorded by the worker', () => {
  const failed = (error_type?: string) =>
    aiFailure({
      quality: {
        analysis: { synthesis: { error_code: 'llm_http_error', http_status: 400, error_type } },
      },
    }).reason;
  expect(failed('BadRequestError:invalid_request_error:output_tokens')).toBe(
    'LLM 호출 실패 (HTTP 400 · BadRequestError · 출력 토큰 한도 초과)',
  );
  expect(failed()).toBe('LLM 호출 실패 (HTTP 400)');
});

it('keeps gauge changes and counter resets distinct from health judgments', () => {
  const metric = (kind: string, a: number, b: number) => ({
    name: `${kind}-${a}-${b}`,
    kind,
    unit: kind === 'counter' ? 'count' : 'celsius',
    gpu_uuid: gpu,
    incident_windows: {
      before: { ...before(a), min: a, last_value: a },
      at_or_after: { ...before(b, '2026-10-22T03:28:43Z'), min: b, last_value: b, samples: 3 },
    },
  });
  const v = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        metrics: [
          metric('gauge', 40, 95),
          metric('gauge', 100, 1),
          metric('counter', 100, 2),
          metric('counter', 100, 0),
        ],
      },
    },
  })!;
  expect(v.metrics.slice(0, 2).map((m) => m.tag)).toEqual(['값 비교', '급감']);
  expect(v.metrics.every((m) => m.tone !== 'ok')).toBe(true);
  expect(v.findings.find((f) => f.key === 'telemetry')!.tone).toBe('warn');
  expect(v.findings.find((f) => f.key === 'telemetry')!.verdict).not.toContain(
    '변화는 보이지 않습니다',
  );
  expect(v.metrics.slice(2).map((m) => m.tag)).toEqual(['누적값 감소', '누적값 감소']);
  expect(v.timeline.some((t) => t.label === '알림 시작')).toBe(true);
  expect(JSON.stringify(v)).not.toContain('알림 수신');
});

it('requires workload observations to bracket the incident time', () => {
  const w = { gpu_uuid: gpu, namespace: 'training', pod: 'worker', last: '2026-10-22T03:28:43Z' };
  const v = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        workloads: [
          { ...w, pod: 'later', first: '2026-10-22T03:28:20Z' },
          { ...w, pod: 'unknown', first: '' },
          { ...w, first: '2026-10-22T03:20:00Z' },
          { ...w, pod: 'earlier', first: '2026-10-22T03:20:00Z', last: '2026-10-22T03:27:59Z' },
        ],
      },
    },
  })!;
  expect(v.workloads.map((w) => w.atIncident)).toEqual([false, false, true, false]);
});

it('builds the same report sections for component alerts from stored Fleet reports', () => {
  const report = (at: string, health: string, reason: string) => ({
    component: 'disk',
    cluster_id: 'cpc-1',
    raw_health: health,
    reason,
    observed_at: at,
    target: { node: 'dgx01', machine_id: 'm-1' },
    evidence_refs: ['log'],
  });
  const ro = 'filesystem remounted as read-only due to errors';
  const v = operatorView({
    runbook_revisions: [{ knowledge_key: 'RB-COMPONENT-DISK', revision: 1 }],
    time_range: { start: '2026-10-23T07:48:50Z', end: '2026-10-23T08:22:06Z' },
    incident_time: '2026-10-23T08:18:50Z',
    missing_inputs: ['report_reason_changed'],
    device_observations: [
      report('2026-10-23T08:16:24Z', 'Healthy', 'ok'),
      report('2026-10-23T08:17:24Z', 'Healthy', 'ok'),
      report('2026-10-23T08:18:24Z', 'Unhealthy', ro),
      report('2026-10-23T08:21:24Z', 'Unhealthy', ro),
    ],
    quality: {
      host_incident_history: {
        schema: 'rca-host-history/1',
        period: { start: '2026-10-09T08:22:06Z', end: '2026-10-23T08:22:06Z' },
        rows: [
          {
            incident_id: 'a',
            current: true,
            codes: [],
            reason: ro,
            occurred_at: '2026-10-23T08:18:50Z',
          },
          {
            incident_id: 'b',
            codes: ['xid:79'],
            gpu_uuid: gpu,
            occurred_at: '2026-10-22T08:00:00Z',
          },
        ],
      },
    },
  })!;
  const [identity, timing, telemetry, repeat, gaps] = v.findings;
  expect([v.family, v.codes, v.node, v.reports]).toEqual(['component', ['disk'], 'dgx01', 2]);
  expect(v.onsetText).toContain('(마지막 정상 보고)');
  expect(identity).toMatchObject({ tone: 'ok', label: '일치' });
  expect(timing.points.join()).toContain('보고 2건');
  expect(telemetry.verdict).toContain('오류·상태 로그로 판단');
  expect(repeat.verdict).toBe('최근 14일 동안 이 노드에서 처음 등록된 disk 사건입니다.');
  expect(repeat.points.join()).not.toContain('NVSwitch 오류(SXID)');
  // Labels are sentences, never internal codes.
  expect(gaps.points[0]).toContain('Fleet 상태 보고(Unhealthy)의 사유가 알람 사유와 다릅니다');
  expect(gaps.points.join()).toContain('장치 식별 정보');
});

it('strips Fleet event-log tags from alert reasons', () => {
  expect(
    plainReason('[Fatal] accelerator-nvidia-error-sxid:  [Potential Fatal] SXID 11001 x'),
  ).toBe('SXID 11001 x');
  expect(plainReason('XID 79 ROBUST')).toBe('XID 79 ROBUST');
});

it('says when no post-incident sample exists yet instead of leading with an idle GPU', () => {
  const pending = (name: string, query: string, last: number) => ({
    name,
    query_id: query,
    unit: 'count',
    kind: 'counter',
    gpu_uuid: gpu,
    last: '2026-10-22T03:27:24Z',
    max_sample_gap_seconds: 240,
    incident_windows: { before: { ...before(last), last_value: last }, at_or_after: null },
  });
  const v = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        metrics: [pending('정정 불가 ECC(DBE) 휘발성 누적값', 'D40', 0)],
      },
    },
  })!;
  expect(v.findings[2].verdict).toBe(
    '사건 뒤 지표 표본이 아직 없습니다(수집 간격 최대 4분). 사건 전 정정 불가 ECC(DBE) 휘발성 누적값은 0 회라 이번 오류가 반영됐는지는 nvidia-smi -q -d ECC로 직접 확인하세요.',
  );
  // XID 79: no post-incident sample yet, so whether the GPU still reports is open.
  expect(v.findings[2].points).toEqual([
    '버스 이탈 확인: 사건 뒤 표본이 아직 없어 판단할 수 없습니다 — Grafana에서 이 GPU 지표가 계속 들어오는지 확인합니다',
  ]);
});

it('reads stored component metrics, row-remap flags and disk bytes', () => {
  const window = (value: number, at: string) => ({
    min: value,
    max: value,
    last_value: value,
    samples: 2,
    first: at,
    last: at,
  });
  const metric = (query: string, name: string, unit: string, kind: string, extra: object) => ({
    query_id: query,
    name,
    unit,
    kind,
    last: '2026-10-23T08:25:00Z',
    max_sample_gap_seconds: 150,
    ...extra,
  });
  const ro = 'filesystem remounted as read-only due to errors';
  const base = (key: string, metrics: object[]) =>
    operatorView({
      runbook_revisions: [{ knowledge_key: key, revision: 2 }],
      time_range: { start: '2026-10-23T07:50:00Z', end: '2026-10-23T08:30:00Z' },
      incident_time: '2026-10-23T08:19:00Z',
      device_observations: [
        {
          component: key === 'RB-COMPONENT-DISK' ? 'disk' : 'accelerator-nvidia-dcgm-mem',
          raw_health: 'Unhealthy',
          reason: ro,
          observed_at: '2026-10-23T08:18:00Z',
          target: { node: 'dgx01' },
        },
      ],
      quality: {
        component_observations: {
          schema: 'rca-component-observations/1',
          event_boundary: '2026-10-23T08:18:00Z',
          metrics,
        },
      },
    })!;
  const mem = base('RB-COMPONENT-DCGM-MEM', [
    metric('D50', '행 재매핑 대기', 'enum', 'enum', {
      gpu_uuid: gpu,
      incident_windows: {
        before: window(0, '2026-10-23T08:10:00Z'),
        at_or_after: window(1, '2026-10-23T08:25:00Z'),
      },
    }),
  ]);
  expect(mem.metrics[0]).toMatchObject({ tag: '리셋 필요', tone: 'warn' });
  expect(mem.metrics[0].afterText).toBe('1 (대기)');
  expect(mem.findings[0].points.join()).toContain('지표 범위: 같은 노드 GPU 1개 전체');
  const disk = base('RB-COMPONENT-DISK', [
    metric('D59', '디스크 사용량 (/)', 'bytes', 'gauge', {
      mount_point: '/',
      incident_windows: {
        before: window(872180035584, '2026-10-23T08:10:00Z'),
        at_or_after: window(872180035584, '2026-10-23T08:25:00Z'),
      },
    }),
  ]);
  // Per-mount rows are not GPU rows: one table, no "GPU 1개" grouping.
  expect(disk.multiGpu).toBe(false);
  expect(disk.metrics[0].beforeText).toBe('872.2 GB');
  expect(valueText(1.888e12, 'B')).toBe('1.9 TB');
});

it('builds a report from the general Runbook and flags a down ethernet link', () => {
  const window = (value: number, at: string) => ({
    min: value,
    max: value,
    last_value: value,
    samples: 2,
    first: at,
    last: at,
  });
  const v = operatorView({
    runbook_revisions: [{ knowledge_key: 'RB-GENERAL-GPU-NODE', revision: 2 }],
    time_range: { start: '2026-10-23T07:50:00Z', end: '2026-10-23T08:30:00Z' },
    incident_time: '2026-10-23T08:19:00Z',
    device_observations: [
      {
        component: 'kubelet',
        raw_health: 'Unhealthy',
        reason: 'kubelet is not running',
        observed_at: '2026-10-23T08:18:00Z',
        target: { node: 'dgx01' },
      },
    ],
    quality: {
      runbook_guidance: [
        {
          report_applicability: 'general_fallback',
          guidance: {
            meaning: '전용 런북이 없어 GPU Node Triage 순서로 조사합니다.',
            next_checks: [],
          },
        },
      ],
      component_observations: {
        schema: 'rca-component-observations/1',
        event_boundary: '2026-10-23T08:18:00Z',
        metrics: [
          {
            query_id: 'D65',
            name: '이더넷 링크 상태 (eth0)',
            interface: 'eth0',
            unit: 'enum',
            kind: 'enum',
            last: '2026-10-23T08:25:00Z',
            max_sample_gap_seconds: 150,
            incident_windows: {
              before: window(1, '2026-10-23T08:10:00Z'),
              at_or_after: window(0, '2026-10-23T08:25:00Z'),
            },
          },
        ],
      },
    },
  })!;
  expect([v.family, v.codes, v.meaning]).toEqual([
    'component',
    ['kubelet'],
    '전용 런북이 없어 GPU Node Triage 순서로 조사합니다.',
  ]);
  expect(v.metrics[0]).toMatchObject({ tag: '링크 끊김', tone: 'alert' });
  expect(v.metrics[0].beforeText).toBe('1 (연결)');
  expect(v.metrics[0].afterText).toBe('0 (끊김)');
  expect(valueText(3, '개')).toBe('3 개');
  expect(valueText(2.5, '')).toBe('2.5');
});

it('keeps node rows apart by load window and interface', () => {
  const window = (value: number, at: string) => ({
    min: value,
    max: value,
    last_value: value,
    samples: 2,
    first: at,
    last: at,
  });
  const row = (query: string, name: string, unit: string, extra: object, v: [number, number]) => ({
    query_id: query,
    name,
    unit,
    kind: 'gauge',
    last: '2026-10-23T08:25:00Z',
    max_sample_gap_seconds: 60,
    incident_windows: {
      before: window(v[0], '2026-10-23T08:10:00Z'),
      at_or_after: window(v[1], '2026-10-23T08:25:00Z'),
    },
    ...extra,
  });
  const v = operatorView({
    runbook_revisions: [{ knowledge_key: 'RB-COMPONENT-CPU', revision: 3 }],
    time_range: { start: '2026-10-23T07:50:00Z', end: '2026-10-23T08:30:00Z' },
    incident_time: '2026-10-23T08:19:00Z',
    device_observations: [
      {
        component: 'cpu',
        raw_health: 'Unhealthy',
        reason: 'error calculating CPU usage',
        observed_at: '2026-10-23T08:18:00Z',
        target: { node: 'dgx01' },
      },
    ],
    quality: {
      component_observations: {
        schema: 'rca-component-observations/1',
        event_boundary: '2026-10-23T08:18:00Z',
        metrics: [
          row('D19', 'CPU 평균 부하 (1분)', 'load', { window: '1m0s' }, [7.44, 11.71]),
          row('D19', 'CPU 평균 부하 (15분)', 'load', { window: '15m0s' }, [7.32, 7.55]),
          row('D68', '이더넷 수신 폐기 누적값 (eth0)', 'packets', { interface: 'eth0' }, [0, 0]),
          row('D68', '이더넷 수신 폐기 누적값 (eth1)', 'packets', { interface: 'eth1' }, [5, 9]),
          {
            ...row('D65', '이더넷 링크 상태 (eth9)', 'enum', { interface: 'eth9' }, [0, 0]),
            kind: 'enum',
          },
          { ...row('D04', 'GPU 온도', 'celsius', { gpu_uuid: gpu }, [40, 41]) },
        ],
      },
    },
  })!;
  expect(v.metrics.map((m) => m.name).sort()).toEqual([
    'CPU 평균 부하 (15분)',
    'CPU 평균 부하 (1분)',
    'GPU 온도',
    '이더넷 링크 상태 (eth9)',
    '이더넷 수신 폐기 누적값 (eth0)',
    '이더넷 수신 폐기 누적값 (eth1)',
  ]);
  // A port already down before the incident is not flagged as this fault.
  expect(v.metrics.find((m) => m.query === 'D65')).toMatchObject({
    tag: '사건 전부터 끊김',
    tone: 'unknown',
  });
  // Host rows are labelled as node metrics, not as one more GPU.
  expect(v.gpuRows.map((r) => r.gpus)).toContain('노드 지표');
  expect(v.metrics.find((m) => m.name === 'CPU 평균 부하 (1분)')!.afterText).toBe('11.71');
});

it('shows how much cumulative counters grew and reads violation time as elapsed time', () => {
  const counter = (query: string, name: string, unit: string, from: number, to: number) => ({
    name,
    query_id: query,
    unit,
    kind: 'counter',
    gpu_uuid: gpu,
    last: '2026-10-22T03:28:40Z',
    max_sample_gap_seconds: 60,
    incident_windows: {
      before: { ...before(from), min: from, last_value: from },
      at_or_after: { ...before(to, '2026-10-22T03:28:40Z'), min: to, last_value: to, samples: 3 },
    },
  });
  const v = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        metrics: [
          counter('D55', 'NVLink CRC 오류 누적값', 'count', 120, 132),
          counter('D62', '전력 제한 누적 시간', 'ns', 3.6e15, 3.6e15 + 1.6e9),
        ],
      },
    },
  })!;
  const crc = v.metrics.find((m) => m.query === 'D55')!;
  expect(crc.afterText).toBe('132 회 (+12 회)');
  expect(crc.short).toBe('사건 뒤 +12 회');
  const power = v.metrics.find((m) => m.query === 'D62')!;
  expect(power.afterText).toBe('41.7일 (+1.6초)');
  expect(valueText(42e9, 'ns')).toBe('42.0초');
});

it('tells an XID 79 GPU that keeps reporting from one that went silent', () => {
  const power = (after: object | null) => ({
    name: 'GPU 전력',
    query_id: 'D11',
    unit: 'W',
    kind: 'gauge',
    gpu_uuid: gpu,
    last: '2026-10-22T03:28:40Z',
    max_sample_gap_seconds: 60,
    incident_windows: { before: { ...before(61), last_value: 61 }, at_or_after: after },
  });
  const v = operatorView({
    quality: {
      triage_observations: {
        ...result.quality.triage_observations,
        metrics: [
          power({ ...before(62, '2026-10-22T03:28:40Z'), min: 62, last_value: 62, samples: 3 }),
        ],
      },
    },
  })!;
  expect(v.findings[2].points[0]).toContain('사건 뒤에도 이 GPU 지표가 3회 새로 들어왔습니다');
  expect(v.findings[2].tone).not.toBe('unknown');
});

it('distinguishes empty switch measurements from unsuccessful collection without internal field names', () => {
  for (const status of ['empty', 'unavailable', 'ok']) {
    const view = operatorView({
      ...result,
      quality: {
        ...result.quality,
        triage_observations: {
          ...result.quality.triage_observations,
          switch_pci: [{ status, reported_pci: ['0000:c6:00.0'], observed_pci: [] }],
        },
      },
    })!;
    const text = view.findings.flatMap((f) => f.points).join(' ');
    expect(text).toContain('0000:c6:00.0');
    expect(text).toContain('Fabric Manager 오류 기록과 포트 상태');
    expect(text).not.toContain('startsAt');
    expect(text).not.toContain('Incident');
    if (status === 'empty') expect(text).toContain('주소 0000:c6:00.0가 붙은 측정 자료는 0건');
    if (status === 'unavailable') {
      expect(text).toContain('측정값 조회가 완료되지 않았습니다');
      expect(text).not.toContain('측정값은 0건');
    }
    if (status === 'ok') expect(text).toContain('장비·기간이 일치하는 자료는 0건');
  }
});
