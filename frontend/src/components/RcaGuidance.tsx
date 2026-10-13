import { rows, str, type Row } from '../lib/live';

// Display only guidance actually stored in this result; retain the full source.
export function RcaGuidance({ paragraphs, result }: { paragraphs: string[]; result: Row }) {
  const text = paragraphs.join('\n');
  const observations = rows(result.device_observations);
  const mismatch = observations.some(
    (o) => o.pci_inventory_relation === 'not_in_reported_inventory',
  );
  const sxid = /SXid|SXID|sxid/.test(text);
  const checks: string[] = [];
  if (/대상|장치|매핑/.test(text))
    checks.push(
      sxid
        ? '어느 NVSwitch에서 발생했는지 확인하세요. 오류의 PCI 주소를 스위치 정보와 대조해야 합니다. 같은 서버의 GPU 목록만으로 오류 장치를 정할 수 없습니다.'
        : `어느 장치에서 발생했는지 확인하세요. ${mismatch ? '오류 로그의 PCI 주소와 수집된 GPU 목록이 일치하지 않습니다. ' : ''}오류 주소와 실제 장치 정보를 대조하고 시험 주입 여부도 확인하세요.`,
    );
  if (/접근|PCIe|NVSwitch/.test(text))
    checks.push(
      sxid
        ? '같은 스위치와 시간대의 오류·연결 상태를 확인하세요. GPU 사용률만으로 스위치 상태나 오류 원인을 판단할 수 없습니다.'
        : '해당 GPU가 현재 정상적으로 인식되는지 확인하세요. 오류가 보고된 시간대의 PCIe 연결 오류 로그도 함께 확인해야 합니다.',
    );
  if (/REBOOT_SYSTEM|RESTART_BM|재시작/.test(text))
    checks.push(
      '재시작을 검토한다면 실행 중인 작업을 안전하게 종료하거나 다른 서버로 옮기세요. 재시작할 서버와 작업 시간을 확인하고 담당자의 승인을 받아야 합니다. 현재 분석만으로 재시작이 필요하다고 확정한 것은 아닙니다.',
    );
  const references = paragraphs.filter((p) =>
    /Fleet 고정 카탈로그|NVIDIA 적용|NVIDIA 조치 분류|Xid 154 연계/.test(p),
  );
  const explain = (p: string) =>
    p
      .replace('Fleet 고정 카탈로그:', 'Fleet의 오류 분류·기본 안내:')
      .replace('GPU has fallen off the bus', 'GPU가 PCIe 연결을 통해 접근되지 않는 오류')
      .replace('event_type=Fatal', '카탈로그 분류: 치명적 오류(이번 장치의 고장 확정은 아님)')
      .replace('기본 action=', '기본 조치 안내: ')
      .replaceAll('REBOOT_SYSTEM', '서버 재시작')
      .replaceAll('HARDWARE_INSPECTION', '하드웨어 점검')
      .replace('NVIDIA 적용:', '문헌에 기재된 GPU 모델:')
      .replace('immediate=RESTART_BM', '즉시 조치 분류: 물리 서버 재시작')
      .replace('investigatory=CONTACT_SUPPORT', '추가 조사: 기술 지원 문의')
      .replace('Xid154 linkage=', 'XID154 연계 조건: ')
      .replace('GPU driver', 'GPU 드라이버');
  return (
    <>
      {checks.length > 0 && (
        <ol>
          {checks.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ol>
      )}
      <p>
        적용 지침:{' '}
        {rows(result.runbook_revisions)
          .map(
            (r) =>
              `${str(r.knowledge_key, str(r.title, 'Runbook'))} · revision ${typeof r.revision === 'number' ? r.revision : str(r.revision, '?')}`,
          )
          .join(', ') || '아래 발행 원문 참조'}
      </p>
      <details className="rca-narrative-more">
        <summary>이 오류에 대한 참고 안내</summary>
        <p>
          아래는 저장된 문헌의 일반 안내입니다. 이번 장비에서 확인된 사실이나 조치 승인과는
          다릅니다.
        </p>
        {references.map((p) => (
          <p key={p}>{explain(p)}</p>
        ))}
        {!references.length && (
          <p>별도 제조사 안내는 저장되어 있지 않습니다. 전체 지침에서 적용 조건을 확인하세요.</p>
        )}
      </details>
      <details className="rca-narrative-more">
        <summary>전체 Runbook 지침·적용 조건·출처 원문</summary>
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </details>
    </>
  );
}
