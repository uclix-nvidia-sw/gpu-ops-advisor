import { rows, str, type Row } from '../lib/live';

// Display only guidance actually stored in this result; retain the full source.
export function RcaGuidance({ paragraphs, result }: { paragraphs: string[]; result: Row }) {
  const text = paragraphs.join('\n');
  const observations = rows(result.device_observations);
  const mismatch = observations.some(
    (o) => o.pci_inventory_relation === 'not_in_reported_inventory',
  );
  const sxid = /SXid|SXID|sxid/.test(text);
  const keys = rows(result.runbook_revisions).map((r) => str(r.knowledge_key));
  const xid79 = keys.includes('RB-XID-79') && /GPU has fallen off the bus/.test(text);
  const sxid11001 = keys.includes('RB-SXID-11001') && /ingress invalid command/.test(text);
  const checks: string[] = [];
  if (/대상|장치|매핑/.test(text))
    checks.push(
      sxid
        ? '어느 NVSwitch에서 발생했는지 확인하세요. 오류의 PCI 주소를 스위치 정보와 대조해야 합니다. 같은 서버의 GPU 목록만으로 오류 장치를 정할 수 없습니다.'
        : `어느 장치에서 발생했는지 확인하세요. ${mismatch ? '오류 로그의 PCI 주소와 수집된 GPU 목록이 일치하지 않습니다. ' : ''}시험 주입 로그인지, 실제 장치에서 발생한 오류인지 먼저 확인해야 합니다. 오류 주소와 실제 장치 정보를 대조하세요.`,
    );
  if (/접근|PCIe|NVSwitch/.test(text))
    checks.push(
      sxid
        ? '같은 스위치와 시간대의 오류·연결 상태를 확인하세요. GPU 사용률만으로 스위치 상태나 오류 원인을 판단할 수 없습니다.'
        : '해당 GPU가 현재 정상적으로 인식되는지 확인하세요. 서버에서 GPU에 접근할 수 있는지 확인하고, 오류가 보고된 시간대의 PCIe 연결 오류 로그를 함께 살펴보세요.',
    );
  if (/REBOOT_SYSTEM|RESTART_BM|재시작/.test(text))
    checks.push(
      '재시작이 필요하다면 서비스 영향을 먼저 확인하세요. 해당 서버에서 실행 중인 작업을 안전하게 종료하거나 다른 서버로 옮기고, 재시작할 서버와 작업 시간을 확인한 뒤 담당자의 승인을 받아 진행하세요. 현재 분석만으로 재시작이 필요하다고 확정한 것은 아닙니다.',
    );
  const references = paragraphs.filter((p) =>
    /Fleet 고정 카탈로그|NVIDIA 적용|NVIDIA 조치 분류|Xid 154 연계/.test(p),
  );
  const referenceRows: [string, string][] = [];
  if (xid79)
    referenceRows.push([
      '어떤 오류인가요?',
      'XID79는 GPU가 PCIe 연결을 통해 접근되지 않는 상황을 나타내는 오류입니다. 이 이름만으로 물리적인 분리나 부품 고장을 확정할 수는 없습니다.',
    ]);
  if (sxid11001)
    referenceRows.push([
      '어떤 오류인가요?',
      'SXID11001은 NVSwitch의 수신 측에서 잘못된 명령을 감지했다는 오류(ingress invalid command)입니다. GPU 자체 고장이나 전체 서버 장애를 뜻한다고 단정할 수는 없습니다.',
    ]);
  if (/기본 action=REBOOT_SYSTEM, HARDWARE_INSPECTION/.test(text))
    referenceRows.push([
      'Fleet의 기본 안내',
      '서버 재시작과 하드웨어 점검을 제시합니다. 이번 장비에서 두 조치가 모두 필요하다는 판정은 아닙니다.',
    ]);
  if (/immediate=RESTART_BM/.test(text) && /investigatory=CONTACT_SUPPORT/.test(text))
    referenceRows.push([
      'NVIDIA 문헌의 조치 안내',
      '물리 서버 재시작과 기술 지원 문의가 제시돼 있습니다. 현재 장비의 상태와 적용 조건을 확인한 뒤 검토해야 합니다.',
    ]);
  const models = text
    .match(/NVIDIA 적용:([^;\n]+)/)?.[1]
    ?.trim()
    .replace(/\.$/, '');
  if (models)
    referenceRows.push([
      '적용 대상 확인',
      `저장된 문헌에는 ${models}이 기재돼 있습니다. 실제 GPU 모델과 문헌의 적용 범위가 맞는지 확인해야 합니다.`,
    ]);
  if (xid79 && /CUDA 12\.7/.test(text) && /R565/.test(text))
    referenceRows.push([
      '추가로 확인할 오류',
      '지원되는 환경에서는 같은 장치·시간대의 XID154 복구 조치 정보를 함께 확인합니다. XID154가 반드시 동반된다는 뜻은 아닙니다. 저장된 연계 조건은 CUDA 12.7·드라이버 R565이며, 자세한 조건은 출처에서 확인합니다.',
    ]);
  if (sxid11001 && /access|trunk/.test(text))
    referenceRows.push([
      '영향 범위 확인',
      '오류가 발생한 스위치 포트와 연결된 GPU·가상 머신·파티션을 확인하세요. GPU에 연결된 포트인지 스위치 사이의 연결 포트인지에 따라 영향 범위가 달라집니다. 전체 시스템 고장으로 단정하지 않습니다.',
    ]);
  if (sxid11001 && /B200\/B300에는 적용하지 않는다/.test(text))
    referenceRows.push([
      '적용 대상 확인',
      '저장된 지침은 B200·B300에 적용하지 않습니다. NVSwitch·Fabric Manager 버전과 물리 서버 또는 가상 머신 운영 방식을 먼저 확인하세요.',
    ]);
  return (
    <>
      {checks.length > 0 && (
        <ol>
          {checks.map((p) => (
            <li key={p}>
              <strong>{p.split(/(?<=\.) /)[0]}</strong>
              <p>
                {p
                  .split(/(?<=\.) /)
                  .slice(1)
                  .join(' ')}
              </p>
            </li>
          ))}
        </ol>
      )}
      <p>
        적용 지침:{' '}
        {rows(result.runbook_revisions)
          .map(
            (r) =>
              `${str(r.knowledge_key).replace(/^RB-(XID|SXID)-(\d+)$/, '$1$2 조사 Runbook') || str(r.title, 'Runbook')} · revision ${typeof r.revision === 'number' ? r.revision : str(r.revision, '?')}`,
          )
          .join(', ') || '아래 발행 원문 참조'}
      </p>
      <details className="rca-narrative-more">
        <summary>이 오류에 대한 참고 안내</summary>
        <p>
          아래는 저장된 문헌의 일반 안내입니다. 이번 장비에서 확인된 사실이나 조치 승인과는
          다릅니다.
        </p>
        <dl className="rca-reference-guide">
          {referenceRows.map(([label, description]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{description}</dd>
            </div>
          ))}
        </dl>
        {!referenceRows.length && references.map((p) => <p key={p}>{p}</p>)}
        {!referenceRows.length && !references.length && (
          <p>별도 제조사 안내는 저장되어 있지 않습니다. 전체 지침에서 적용 조건을 확인하세요.</p>
        )}
      </details>
      <details className="rca-narrative-more">
        <summary>제조사 안내·적용 조건·원문 보기</summary>
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </details>
    </>
  );
}
