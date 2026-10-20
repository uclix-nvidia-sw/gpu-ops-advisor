import { obj, rows, str, strings, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';

function eventTime(value: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return '발생 시각 미기록';
  return (
    new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(value)) + ' KST'
  );
}

export function RcaObservations({
  result,
  onEvidence,
}: {
  result: Row;
  onEvidence?: (id: string) => void;
}) {
  const observations = rows(result.device_observations);
  const analysis = obj(obj(result.quality).analysis);
  const events = rows(analysis.error_events);
  if (!observations.length && !events.length) return null;
  const evidence = (value: unknown) =>
    strings(value).length
      ? strings(value).map((id) =>
          onEvidence ? (
            <button className="text-link" key={id} onClick={() => onEvidence(id)}>
              {id}
            </button>
          ) : (
            <code key={id}>{id} </code>
          ),
        )
      : '근거 ID 미기록';
  const missingTime = observations.filter(
    (o) => o.producer_time_status === 'missing_or_zero',
  ).length;
  const unverified = observations.filter((o) => o.fact_eligible === false).length;
  return (
    <section className="result-section" aria-label="관측 근거 요약">
      <h3>관측 근거: 확인한 사실과 판단 제한</h3>
      <p>
        오류 이벤트 {Array.isArray(analysis.error_events) ? `${events.length}건` : '미기록'} · 상태
        보고 {Array.isArray(result.device_observations) ? `${observations.length}건` : '미기록'}.
        서로 다른 종류의 관측이며 현재 상태·장애 횟수·원인 확정과 구분합니다.
      </p>
      {events.length > 0 && (
        <details open>
          <summary>오류 이벤트·보고된 장치 연결</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>보고된 오류·대상</th>
                  <th>이벤트 시각·기록 시각</th>
                  <th>장치 연결·판단 제한</th>
                  <th>근거</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event, i) => (
                  <tr key={i}>
                    <td>
                      {str(event.error_code, '오류 코드 미기록')} · 오류 이벤트 보고
                      <p>
                        클러스터 {str(event.cluster_id, '미기록')} · 노드{' '}
                        {str(obj(event.target).node, '미기록')}
                      </p>
                      <p>
                        보고된 장치: <code>{str(event.reported_device, '미기록')}</code>
                      </p>
                    </td>
                    <td>
                      {event.time_basis === 'producer_event_time'
                        ? '생산자 이벤트 시각'
                        : `시각 기준: ${str(event.time_basis, '미기록')}`}
                      <p>
                        {eventTime(str(event.event_time))} ·{' '}
                        <code>{str(event.event_time, '미기록')}</code>
                      </p>
                      <p>
                        Loki 기록 시각 (Unix ns):{' '}
                        <code>{str(event.loki_timestamp_ns, '미기록')}</code>
                      </p>
                    </td>
                    <td>
                      {event.device_mapping === 'inventory_match'
                        ? '수집된 GPU 목록과 주소 일치'
                        : event.device_mapping === 'conflicting'
                          ? '보고된 장치 식별자 상충'
                          : event.device_mapping === 'unresolved'
                            ? '장치 연결 미확정'
                            : `장치 연결: ${str(event.device_mapping, '미기록')}`}
                      {event.inventory_gpu_candidate != null && (
                        <p>
                          저장된 GPU 연결 후보: <code>{str(event.inventory_gpu_candidate)}</code>
                        </p>
                      )}
                      <p>
                        로그가 어느 장치를 가리키는지 대조한 결과입니다. 장비를 직접 점검하거나 복구
                        작업을 수행한 결과는 아닙니다.
                      </p>
                      {strings(event.limitations)
                        .filter((limit) => limit !== 'device_identity_not_independently_verified')
                        .map((limit) => (
                          <p key={limit}>
                            {(
                              {
                                current_health_unverified: '현재 상태 미검증',
                                physical_or_synthetic_origin_unverified:
                                  '실제 장애·시험 주입 여부 미검증',
                              } as Record<string, string>
                            )[limit] || limit}
                          </p>
                        ))}
                    </td>
                    <td>
                      {evidence(event.evidence_refs)}
                      {event.event_id != null && (
                        <p>
                          이벤트 ID: <code>{str(event.event_id)}</code>
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {observations.length > 0 && (
        <>
          <p>
            상태 보고 {observations.length}건 중 생산자 시각 누락·초기값 {missingTime}건, 현재 상태
            근거로 미검증 {unverified}건입니다. 로그 기록 시각은 실제 오류 발생 시각과 다를 수
            있습니다.
          </p>
          <details>
            <summary>상태 보고·장치 연결 상세</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>보고 시각</th>
                    <th>오류 코드·상태 해석</th>
                    <th>장치 연결</th>
                    <th>판단 제한</th>
                    <th>근거</th>
                  </tr>
                </thead>
                <tbody>
                  {observations.map((o, i) => (
                    <tr key={i}>
                      <td>
                        {formatDate(str(o.observed_at))}
                        <br />
                        {str(o.time_basis) === 'loki_recorded_at'
                          ? 'Loki 기록 시각'
                          : '시각 기준 원문 확인'}
                        <p>
                          <code>{str(o.observed_at, '시각 미기록')}</code>
                        </p>
                      </td>
                      <td>
                        {str(o.error_code, '오류 코드 미확인')} ·{' '}
                        {o.normalized_health === 'unhealthy'
                          ? '이상 상태로 보고됨'
                          : o.normalized_health === 'healthy'
                            ? '정상 상태로 보고됨'
                            : '상태 의미 미확인'}
                      </td>
                      <td>
                        {o.pci_inventory_relation === 'switch_inventory_required'
                          ? 'NVSwitch 정보 대조 필요(GPU 목록과 비교 불가)'
                          : o.pci_inventory_relation === 'not_in_reported_inventory'
                            ? '오류 PCI와 GPU 목록 불일치'
                            : o.pci_inventory_relation === 'inventory_candidate_only'
                              ? '오류에 적힌 주소가 수집된 GPU 목록과 일치'
                              : `현재 정보만으로 오류 장치 확정 불가 · ${str(o.pci_inventory_relation, '연결 상태 미기록')}`}
                        {strings(o.reported_pci_addresses).length > 0 && (
                          <p>보고된 PCI: {strings(o.reported_pci_addresses).join(', ')}</p>
                        )}
                        {rows(o.gpu_candidates).length > 0 && (
                          <details>
                            <summary>수집된 GPU 목록 · 각 GPU의 장애 여부와 구분</summary>
                            {rows(o.gpu_candidates).map((gpu, j) => (
                              <p key={j}>
                                <code>{str(gpu.gpu_uuid, 'UUID 미기록')}</code> ·{' '}
                                <code>{str(gpu.bus_id, 'PCI 미기록')}</code>
                              </p>
                            ))}
                          </details>
                        )}
                      </td>
                      <td>
                        {o.fact_eligible === false
                          ? '현재 장치 상태 판정에 사용할 조건 미충족'
                          : '원본 계약·시각·대상 조건 확인'}
                        {o.producer_time_status === 'missing_or_zero' ? ' · 생산자 시각 없음' : ''}
                      </td>
                      <td>{evidence(o.evidence_refs)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
