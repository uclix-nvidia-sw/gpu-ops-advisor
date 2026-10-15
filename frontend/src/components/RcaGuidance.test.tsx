import { readFileSync } from 'node:fs';

import { it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaGuidance } from './RcaGuidance';
import { RcaObservations } from './RcaObservations';

// Read canonical Runbooks only when tests execute; production builds contain frontend only.
const xid = JSON.parse(
  readFileSync(new URL('../../../rcca-agent/runbooks/xid/RB-XID-79.json', import.meta.url), 'utf8'),
);
const sxid = JSON.parse(
  readFileSync(
    new URL('../../../rcca-agent/runbooks/sxid/RB-SXID-11001.json', import.meta.url),
    'utf8',
  ),
);

it('keeps literature separate from device facts and explains restart prerequisites', () => {
  const paragraphs = [
    '대상 장치 접근을 확인한다.',
    'Fleet 고정 카탈로그: GPU has fallen off the bus; event_type=Fatal; 기본 action=REBOOT_SYSTEM, HARDWARE_INSPECTION.',
  ];
  const result = {
    quality: {
      runbook_guidance: [
        {
          title: xid.content.title,
          revision: 5,
          guidance: xid.content.operator_guidance,
          sources: xid.content.sources,
        },
      ],
    },
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaGuidance paragraphs={paragraphs} result={result} />);
  expect(html).toContain('작업 배출·유지보수 승인 후 재시작합니다');
  expect(html).toContain('복구에는 재시작이 필요합니다');
  expect(html).toContain('revision 5');
  expect(html).toContain('<details><summary>적용 지침</summary><p>');
  expect(html).toContain('<h5 class="rca-reference-heading">이 오류에 대한 참고 안내</h5>');
  expect(html).not.toContain('<details open');
  expect(html).not.toContain('현재는 연결되지 않았습니다');
  expect(JSON.stringify(result)).toBe(before);
});

it('separates switch inventory, missing producer time and unverified health', () => {
  const result = {
    device_observations: [
      {
        observed_at: '2026-10-13T02:44:00Z',
        time_basis: 'loki_recorded_at',
        error_code: 'sxid:11001',
        fact_eligible: false,
        producer_time_status: 'missing_or_zero',
        pci_inventory_relation: 'switch_inventory_required',
      },
    ],
  };
  const html = renderToStaticMarkup(<RcaObservations result={result} />);
  expect(html).toContain('NVSwitch 정보 대조 필요');
  expect(html).toContain('GPU 목록과 비교 불가');
  expect(html).toContain('생산자 시각 누락·초기값 1건');
  expect(html).not.toContain('오류 PCI와 GPU 목록 불일치');
  expect(renderToStaticMarkup(<RcaObservations result={{}} />)).toBe('');
});

it('shows a matched address and event identity without declaring current health', () => {
  const result = {
    quality: {
      analysis: {
        error_events: [
          {
            event_time: '2026-10-15T04:17:48Z',
            cluster_id: 'cluster-a',
            target: { node: 'node-a' },
            error_code: 'xid:79',
            reported_device: '0000:07:00',
            device_mapping: 'inventory_match',
            inventory_gpu_candidate: 'GPU-matched',
          },
        ],
      },
    },
    device_observations: [
      { pci_inventory_relation: 'inventory_candidate_only', fact_eligible: false },
    ],
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaObservations result={result} />);
  expect(html).toContain('GPU-matched');
  expect(html).toContain('13:17:48 KST');
  expect(html).toContain('오류 PCI 주소가 수집 GPU 인벤토리와 일치');
  expect(html).not.toContain('현재 정보만으로 오류 장치 확정 불가');
  expect(html).toContain('현재 접근 상태와 업무 영향은 별도 관측');
  expect(JSON.stringify(result)).toBe(before);
});

it('explains SXID11001 without GPU failure or XID restart guidance', () => {
  const html = renderToStaticMarkup(
    <RcaGuidance
      paragraphs={[
        'SXID 대상 NVSwitch ingress invalid command; access/trunk. B200/B300에는 적용하지 않는다.',
      ]}
      result={{
        quality: {
          runbook_guidance: [
            {
              title: sxid.content.title,
              revision: 4,
              guidance: sxid.content.operator_guidance,
              sources: sxid.content.sources,
            },
          ],
        },
      }}
    />,
  );
  expect(html).toContain('수신(ingress) 측에서 잘못된 명령');
  expect(html).not.toContain('단정할 수는 없습니다');
  expect(html).toContain('B200·B300에는 이 지침을 적용하지 않습니다');
  expect(html).not.toContain('XID154');
  expect(html).not.toContain('GPU가 PCIe 연결을 통해');
});
it('does not invent catalog details for unknown or unrecorded guidance', () => {
  const html = renderToStaticMarkup(
    <RcaGuidance
      paragraphs={['대상 확인']}
      result={{ runbook_revisions: [{ knowledge_key: 'RB-XID-79', revision: 4 }] }}
    />,
  );
  expect(html).not.toContain('물리 서버 재시작과 기술 지원 문의');
  expect(html).not.toContain('GPU가 PCIe 연결을 통해');
});

it('renders a new error family from its published guidance without UI code branches', () => {
  const guidance = structuredClone(xid.content.operator_guidance);
  guidance.meaning = '새 구성 요소의 관측 오류 설명';
  guidance.cause_note = '원인은 별도 검증';
  guidance.next_checks = [{ title: '원본 상태 확인', text: '같은 대상의 기록을 확인하세요.' }];
  guidance.references = [
    { title: '해당 생산자 안내', text: '전용 출처의 적용 조건', source_indices: [0] },
  ];
  const html = renderToStaticMarkup(
    <RcaGuidance
      paragraphs={[]}
      result={{
        quality: {
          runbook_guidance: [
            { title: '새 오류 조사', revision: 1, guidance, sources: xid.content.sources },
          ],
        },
      }}
    />,
  );
  expect(html).toContain('새 구성 요소의 관측 오류 설명');
  expect(html).not.toContain('XID154');
  expect(html).not.toContain('재시작');
});
