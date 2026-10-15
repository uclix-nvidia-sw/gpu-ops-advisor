import { obj, rows, str, type Row } from '../lib/live';
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

export function RcaObservations({ result }: { result: Row }) {
  const observations = rows(result.device_observations);
  const events = rows(obj(obj(result.quality).analysis).error_events);
  if (!observations.length && !events.length) return null;
  const missingTime = observations.filter(
    (o) => o.producer_time_status === 'missing_or_zero',
  ).length;
  const unverified = observations.filter((o) => o.fact_eligible === false).length;
  return (
    <section className="result-section" aria-label="관측 근거 요약">
      <h3>관측 근거: 확인한 사실과 판단 제한</h3>
      {events.length > 0 && (
        <section aria-label="오류 이벤트·장치 연결">
          <h4>오류 이벤트·장치 연결</h4>
          <ul>
            {events.map((event, i) => (
              <li key={i}>
                {eventTime(str(event.event_time))} (생산자 이벤트 시각) · {str(event.cluster_id)} /{' '}
                {str(obj(event.target).node)} ·{' '}
                {str(event.error_code).toUpperCase().replace(':', ' ')} ·{' '}
                {str(event.reported_device)}
                <p>
                  {event.device_mapping === 'inventory_match'
                    ? `오류 장치 주소와 수집 GPU 인벤토리 일치: ${str(event.inventory_gpu_candidate)}`
                    : event.device_mapping === 'conflicting'
                      ? '이벤트 내부 장치 식별자 충돌'
                      : str(event.error_code).startsWith('sxid:')
                        ? 'NVSwitch·포트 연결 근거 미확보'
                        : '장치 연결 근거 미확보'}
                </p>
                <p>
                  이벤트 발생 기록입니다. 현재 접근 상태와 업무 영향은 별도 관측으로 확인합니다.
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p>
        상태 보고 {observations.length}건 중 생산자 시각 누락·초기값 {missingTime}건, 현재 상태
        근거로 미검증 {unverified}건입니다. 로그 기록 시각은 실제 오류 발생 시각과 다를 수 있습니다.
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
                          ? '오류 PCI 주소가 수집 GPU 인벤토리와 일치'
                          : '이 상태 보고에는 오류 장치 연결 근거가 없습니다'}
                  </td>
                  <td>
                    {o.fact_eligible === false
                      ? '현재 장치 상태 판정에 사용할 조건 미충족'
                      : '원본 계약·시각·대상 조건 확인'}
                    {o.producer_time_status === 'missing_or_zero' ? ' · 생산자 시각 없음' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
