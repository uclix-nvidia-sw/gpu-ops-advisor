import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaObservations } from './RcaObservations';

const event = {
  error_code: 'xid:79',
  event_time: '2026-10-15T01:33:48Z',
  time_basis: 'producer_event_time',
  loki_timestamp_ns: '1792028028000000000',
  reported_device: 'PCI:0000:07:00',
  device_mapping: 'inventory_match',
  inventory_gpu_candidate: 'GPU-fixture',
  target: { node: 'fixture-node' },
  cluster_id: 'fixture-cluster',
  fact_eligible: false,
  limitations: ['current_health_unverified', 'device_identity_not_independently_verified'],
  evidence_refs: ['event-evidence'],
};

it('renders event-only evidence and a reported inventory match without upgrading identity', () => {
  const result = { quality: { analysis: { error_events: [event] } } };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaObservations result={result} onEvidence={() => {}} />);
  for (const text of [
    '오류 이벤트 1건',
    '상태 보고 미기록',
    '생산자 이벤트 시각',
    event.event_time,
    event.loki_timestamp_ns,
    '수집된 GPU 목록과 주소 일치',
    'GPU-fixture',
    'event-evidence',
  ])
    expect(html).toContain(text);
  expect(html).toContain('<button');
  expect(html).not.toContain('생산자 시각 없음');
  expect(html).not.toContain('장치 신원 독립 검증 없음');
  expect(JSON.stringify(result)).toBe(before);
});

it('separates missing report time from event time and does not choose a GPU from inventory', () => {
  const html = renderToStaticMarkup(
    <RcaObservations
      result={{
        quality: { analysis: { error_events: [event] } },
        device_observations: [
          {
            observed_at: '2026-10-15T02:00:00Z',
            time_basis: 'loki_recorded_at',
            producer_time_status: 'missing_or_zero',
            pci_inventory_relation: 'inventory_candidate_only',
            reported_pci_addresses: ['PCI:0000:07:00'],
            gpu_candidates: [{ gpu_uuid: 'GPU-other', bus_id: '0000:08:00.0' }],
            evidence_refs: ['status-evidence'],
            fact_eligible: false,
          },
        ],
      }}
    />,
  );
  for (const text of [
    '생산자 시각 누락·초기값 1건',
    '생산자 이벤트 시각',
    'Loki 기록 시각',
    '오류에 적힌 주소가 수집된 GPU 목록과 일치',
    '수집된 GPU 목록 · 각 GPU의 장애 여부와 구분',
    'GPU-other',
    'status-evidence',
  ])
    expect(html).toContain(text);
  expect(html).toMatch(
    /<td>현재 장치 상태 판정에 사용할 조건 미충족 · 생산자 시각 없음<\/td><td><code>status-evidence/,
  );
});

it.each(['conflicting', 'unresolved', 'future_mapping'])(
  'keeps mapping %s unresolved and escapes raw values',
  (mapping) => {
    const html = renderToStaticMarkup(
      <RcaObservations
        result={{
          quality: {
            analysis: {
              error_events: [
                {
                  ...event,
                  device_mapping: mapping,
                  inventory_gpu_candidate: null,
                  reported_device: '<script>bad</script>',
                  limitations: ['future_limit'],
                },
              ],
            },
          },
        }}
      />,
    );
    expect(html).not.toContain('보고된 재고와 연결 일치');
    expect(html).not.toContain('<script>');
    expect(html).toContain('future_limit');
    expect(html).not.toContain('GPU-fixture');
  },
);
