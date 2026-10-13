import { rows, str, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';

export function RcaObservations({ result }: { result: Row }) {
  const observations = rows(result.device_observations);
  if (!observations.length) return null;
  const missingTime = observations.filter(
    (o) => o.producer_time_status === 'missing_or_zero',
  ).length;
  const unverified = observations.filter((o) => o.fact_eligible === false).length;
  return (
    <section className="result-section" aria-label="관측 근거 요약">
      <h3>관측 근거: 확인한 사실과 판단 제한</h3>
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
                        : '현재 정보만으로 오류 장치 확정 불가'}
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
