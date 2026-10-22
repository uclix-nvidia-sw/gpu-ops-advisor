import { useState } from 'react';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';

const phaseNames: Record<string, string> = {
  Pending: '실행 대기',
  Running: '실행 중',
  Succeeded: 'Pod 성공 종료',
  Failed: 'Pod 실패 종료',
};

export function WorkloadContext({
  value,
  onEvidence,
}: {
  value: Row;
  onEvidence?: (id: string) => void;
}) {
  const [showRecords, setShowRecords] = useState(false);
  if (!value.version) return null;
  const records = rows(value.records);
  const groups = new Map<string, Row[]>();
  for (const record of records) {
    const key = JSON.stringify([record.cluster_id, record.namespace, record.workload_type]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(record);
  }
  return (
    <details className="aggregate-evidence">
      <summary>작업 유형·GPU 요청·노드 배정 근거</summary>
      <p className="aggregate-static-note">
        당시 작업 라벨과 상태를 연결한 보충 자료입니다. GPU 요청량은 실제 할당량이 아니며, 테스트
        유형은 실제 서빙·학습 목적과 구분합니다.
      </p>
      {!records.length ? (
        <p>
          같은 시간대에 연결할 작업 자료가 없습니다. 기존 대기·완료 수치를 0으로 바꾸지 않습니다.
        </p>
      ) : (
        <div className="aggregate-table-scroll">
          <table>
            <caption>연결된 작업 일부의 관측 범위</caption>
            <thead>
              <tr>
                <th>클러스터 / Namespace</th>
                <th>연결된 라벨</th>
                <th>작업 라벨의 의미</th>
                <th>Pod별 GPU 요청 범위</th>
                <th>관측 상태</th>
              </tr>
            </thead>
            <tbody>
              {[...groups.entries()].map(([key, items]) => {
                const first = items[0];
                const labels = [
                  ...new Set(
                    items.flatMap((r) =>
                      ['profile', 'execution', 'queue_design'].flatMap((field) =>
                        str(r[field])
                          ? [`gpu-report-test-${field.replace('_', '-')}=${str(r[field])}`]
                          : [],
                      ),
                    ),
                  ),
                ];
                const amounts = items.map((r) => Number(r.regular_gpu_request));
                const min = Math.min(...amounts),
                  max = Math.max(...amounts);
                const states = [
                  ...new Set(
                    items.map(
                      (r) =>
                        `${phaseNames[str(r.phase)] || '상태 미확인'} · ${r.node ? '노드 배정됨' : '노드 배정 안 됨'}`,
                    ),
                  ),
                ];
                return (
                  <tr key={key}>
                    <th>
                      {str(first.cluster_id)}
                      <br />
                      {str(first.namespace)}
                    </th>
                    <td>
                      {labels.length
                        ? labels.map((label) => (
                            <div key={label}>
                              <code>{label}</code>
                            </div>
                          ))
                        : '연결된 라벨 자료 없음'}
                    </td>
                    <td>{str(first.workload_type)}</td>
                    <td>
                      {min === max ? min : `${min}~${max}`}개<br />
                      <small>일반 컨테이너 요청 합계</small>
                    </td>
                    <td>{states.join(' / ')}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {rows(value.completed_jobs).length > 0 && (
        <div className="aggregate-table-scroll">
          <table>
            <caption>기존 완료 Job에 연결한 작업 유형</caption>
            <thead>
              <tr>
                <th>클러스터 / Namespace</th>
                <th>완료 Job</th>
                <th>연결한 유형</th>
              </tr>
            </thead>
            <tbody>
              {rows(value.completed_jobs).map((j) => (
                <tr key={`${j.cluster_id}/${j.namespace}/${j.job_name}/${j.created_at}`}>
                  <td>
                    {str(j.cluster_id)}
                    <br />
                    {str(j.namespace)}
                  </td>
                  <td>{str(j.job_name)}</td>
                  <td>{str(j.workload_type)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details onToggle={(event) => setShowRecords(event.currentTarget.open)}>
        <summary>작업별 시간대와 근거 보기</summary>
        <div className="aggregate-table-scroll">
          <table>
            <caption>동일 Pod UID로 연결한 시간대별 자료 · KST · 종료 시각 제외</caption>
            <thead>
              <tr>
                <th>클러스터 / Namespace / Pod</th>
                <th>관측 시간대</th>
                <th>노드 / 상태</th>
                <th>GPU 요청</th>
                <th>근거</th>
              </tr>
            </thead>
            <tbody>
              {showRecords &&
                records.map((r) => (
                  <tr key={`${r.cluster_id}/${r.uid}/${obj(r.period).start}`}>
                    <th>
                      {str(r.cluster_id)} / {str(r.namespace)}
                      <br />
                      {str(r.pod)}
                    </th>
                    <td>
                      {reportRequestTime(str(obj(r.period).start))}
                      <br />~ {reportRequestTime(str(obj(r.period).end))}
                    </td>
                    <td>
                      {str(r.node) || '노드 배정 안 됨'}
                      <br />
                      {phaseNames[str(r.phase)] || '미확인'}
                    </td>
                    <td>{String(r.regular_gpu_request)}개</td>
                    <td>
                      {strings(r.evidence_refs).map((id, i) =>
                        onEvidence ? (
                          <button
                            type="button"
                            className="text-link"
                            key={id}
                            onClick={() => onEvidence(id)}
                          >
                            근거 {i + 1}
                          </button>
                        ) : (
                          <span key={id}>저장 근거 {i + 1}</span>
                        ),
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="aggregate-static-note">
        이 표의 범위는 여러 시점의 관측을 묶은 것으로 동시 요청 총량이 아닙니다. 제외된 연결 표본:{' '}
        {String(value.excluded_records ?? 0)}건.
      </p>
      {strings(value.limitations).map((note) => (
        <p className="aggregate-static-note" key={note}>
          {note}
        </p>
      ))}
    </details>
  );
}
