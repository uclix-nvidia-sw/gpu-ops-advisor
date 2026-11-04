// Shared reference table; placement never recommends a reset for the incident.
export function RcaResetGuide() {
  return (
    <details className="rca-reset-guide">
      <summary>GPU·NVSwitch 리셋 방식 선택 (NVIDIA GPU Node Triage 표 2)</summary>
      <div className="rca-history-table">
        <table>
          <thead>
            <tr>
              <th>구성</th>
              <th>리셋 방식</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Ampere+ NVSwitch · bare metal · FM 실행 중</td>
              <td>GPU 개별 리셋 가능, FM이 해당 NVSwitch 링크를 함께 리셋</td>
            </tr>
            <tr>
              <td>Ampere+ NVSwitch · bare metal · FM 미실행</td>
              <td>개별 리셋 불가, NVLink로 연결된 GPU·NVSwitch 전체 리셋</td>
            </tr>
            <tr>
              <td>Hopper+ NVSwitch · bare metal</td>
              <td>개별 리셋 지원, -i 없이 nvidia-smi 리셋 시 전체 리셋</td>
            </tr>
            <tr>
              <td>가상화(VM 안의 GPU)</td>
              <td>GPU 리셋 미지원 → VM 재시작 (Hopper+는 하이퍼바이저 권한에 따라 다름)</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="rca-muted">
        리셋은 대상 GPU를 쓰는 프로세스가 없어야 하며 root 권한이 필요합니다. 작업 배출 후
        수행합니다.
      </p>
    </details>
  );
}
