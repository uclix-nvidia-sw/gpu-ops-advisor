import { it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaGuidance } from './RcaGuidance';
import { RcaObservations } from './RcaObservations';

it('keeps literature separate from device facts and explains restart prerequisites', () => {
  const paragraphs = [
    '대상 장치 접근을 확인한다.',
    'Fleet 고정 카탈로그: GPU has fallen off the bus; event_type=Fatal; 기본 action=REBOOT_SYSTEM, HARDWARE_INSPECTION.',
  ];
  const result = { runbook_revisions: [{ knowledge_key: 'RB-XID-79', revision: 4 }] };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaGuidance paragraphs={paragraphs} result={result} />);
  expect(html).toContain('안전하게 종료하거나 다른 서버로 옮기고');
  expect(html).toContain('물리적인 분리나 부품 고장을 확정할 수는 없습니다');
  expect(html).toContain('XID79 조사 Runbook · revision 4');
  expect(html).toContain('<summary>이 오류에 대한 참고 안내</summary>');
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

it('explains SXID11001 without GPU failure or XID restart guidance', () => {
  const html = renderToStaticMarkup(
    <RcaGuidance
      paragraphs={[
        'SXID 대상 NVSwitch ingress invalid command; access/trunk. B200/B300에는 적용하지 않는다.',
      ]}
      result={{ runbook_revisions: [{ knowledge_key: 'RB-SXID-11001', revision: 3 }] }}
    />,
  );
  expect(html).toContain('수신 측에서 잘못된 명령');
  expect(html).toContain('전체 시스템 고장으로 단정하지 않습니다');
  expect(html).toContain('B200·B300에 적용하지 않습니다');
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
