import { rows, str, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';

function StoredTime({ value }: { value: string }) {
  const formatted = reportRequestTime(value);
  return (
    <time dateTime={value}>
      <span>{formatted.slice(0, -9)}</span>
      <span>{formatted.slice(-8)}</span>
    </time>
  );
}

export function WorkloadCharts({ workloads }: { workloads: Row[] }) {
  return (
    <div className="aggregate-workload-charts">
      <h4>클러스터별 작업 대기·완료</h4>
      <p className="aggregate-static-note">
        대기 그래프는 시간 구간의 최대 Pod 수입니다. 선으로 연결한 순간 상태나 대기 시간이 아닙니다.
        Job 경과시간은 시작부터 완료까지이며 대기·준비를 포함합니다. 보고 기간에 완료된 이전 실행
        작업도 포함됩니다.
      </p>
      {[...new Set(workloads.map((w) => str(w.cluster_id)))].map((cluster) => {
        const clusterWorkloads = workloads.filter((w) => str(w.cluster_id) === cluster);
        const maximum = Math.max(
          1,
          ...clusterWorkloads.flatMap((w) => rows(w.hours).map((h) => Number(h.pending_peak) || 0)),
        );
        const jobs: Row[] = clusterWorkloads.flatMap((w) =>
          rows(w.completed_jobs).map((j) => ({ ...j, namespace: w.namespace })),
        );
        const maxElapsed = Math.max(1, ...jobs.map((j) => Number(j.elapsed_seconds) || 0));
        const pendingHighlights = clusterWorkloads.flatMap((w) => {
          const hours = rows(w.hours).filter(
            (h) => typeof h.pending_peak === 'number' && h.pending_peak > 0,
          );
          if (!hours.length) return [];
          const peak = Math.max(...hours.map((h) => Number(h.pending_peak)));
          const firstPeak = hours.find((h) => h.pending_peak === peak)!;
          return [{ namespace: str(w.namespace), peak, firstPeak }];
        });
        pendingHighlights.sort((a, b) => b.peak - a.peak || a.namespace.localeCompare(b.namespace));
        const shownPendingHighlights = pendingHighlights.slice(0, 3);
        return (
          <section
            key={cluster}
            className="aggregate-chart"
            aria-label={`${cluster} 작업 대기·완료`}
          >
            <div className="aggregate-chart-heading">
              <h4>{cluster} 클러스터</h4>
            </div>
            <section className="aggregate-metric-chart">
              <h5 className="aggregate-chart-metric-title">시간대별 최대 대기 Pod 수 (개)</h5>
              {pendingHighlights.length ? (
                <ul className="aggregate-workload-highlights">
                  {shownPendingHighlights.map(({ namespace, peak, firstPeak }) => (
                    <li key={namespace}>
                      <strong>{namespace}</strong> · 최대 {peak}개 ·{' '}
                      {reportRequestTime(str(firstPeak.start)).slice(0, -9)}{' '}
                      {reportRequestTime(str(firstPeak.start)).slice(-8, -3)}–
                      {reportRequestTime(str(firstPeak.end)).slice(-8, -3)}
                    </li>
                  ))}
                  {pendingHighlights.length > shownPendingHighlights.length && (
                    <li>
                      그 외 {pendingHighlights.length - shownPendingHighlights.length}개 Namespace는
                      상세 보기
                    </li>
                  )}
                </ul>
              ) : (
                <p>
                  {clusterWorkloads.some((w) =>
                    rows(w.hours).some((h) => typeof h.pending_peak === 'number'),
                  )
                    ? '관측된 시간대에 대기 Pod가 없었습니다.'
                    : '대기 관측 자료가 없습니다.'}
                </p>
              )}
              <p className="aggregate-workload-caption">
                첫 최대 관측 시간대입니다. 대기 시간은 아닙니다.
              </p>
              <details className="aggregate-workload-detail">
                <summary>Namespace별 모든 시간대 보기</summary>
                {clusterWorkloads.map((w) => {
                  const hours = rows(w.hours).filter((h) => typeof h.pending_peak === 'number');
                  return (
                    <div
                      key={str(w.namespace)}
                      className="aggregate-workload-namespace"
                      aria-label={`${cluster} ${w.namespace} 대기 관측`}
                    >
                      <h6>{str(w.namespace)}</h6>
                      {!hours.length ? (
                        <p>대기 자료 없음</p>
                      ) : (
                        <figure
                          className="rca-bars"
                          aria-label={`${w.namespace} 시간대별 최대 대기 Pod 수`}
                        >
                          {hours.map((h) => (
                            <div
                              className="rca-bar"
                              key={str(h.start)}
                              aria-label={`최대 대기 ${h.pending_peak}개`}
                              title={`${reportRequestTime(str(h.start))} ~ ${reportRequestTime(str(h.end))}`}
                            >
                              <span className="aggregate-workload-period">
                                <span>{reportRequestTime(str(h.start)).slice(0, -9)}</span>
                                <strong>
                                  {reportRequestTime(str(h.start)).slice(-8, -3)}–
                                  {reportRequestTime(str(h.end)).slice(-8, -3)}
                                </strong>
                              </span>
                              <span className="rca-bar-track">
                                <span
                                  style={{ width: `${(Number(h.pending_peak) / maximum) * 100}%` }}
                                />
                              </span>
                              <strong>{Number(h.pending_peak)}개</strong>
                            </div>
                          ))}
                        </figure>
                      )}
                    </div>
                  );
                })}
              </details>
            </section>
            <section className="aggregate-metric-chart">
              <h5 className="aggregate-chart-metric-title">완료 Job별 경과시간 · 대기·준비 포함</h5>
              {!jobs.length ? (
                <p>확인된 완료 표본 없음</p>
              ) : (
                <div className="aggregate-table-scroll">
                  <table className="aggregate-workload-table">
                    <caption className="sr-only">{cluster} 완료 Job별 시작·완료와 경과시간</caption>
                    <colgroup>
                      <col className="aggregate-workload-name-column" />
                      <col />
                      <col />
                      <col />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>Namespace / Job</th>
                        <th>시작 (KST)</th>
                        <th>완료 (KST)</th>
                        <th>경과시간</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={`${j.namespace}/${j.job_name}`}>
                          <th scope="row" className="aggregate-workload-job">
                            {str(j.namespace)}
                            <span>{str(j.job_name)}</span>
                          </th>
                          <td className="aggregate-date">
                            <StoredTime value={str(j.started_at)} />
                          </td>
                          <td className="aggregate-date">
                            <StoredTime value={str(j.completed_at)} />
                          </td>
                          <td>
                            <strong className="aggregate-workload-duration">
                              {Math.floor(Number(j.elapsed_seconds) / 60)}분{' '}
                              {Number(j.elapsed_seconds) % 60}초
                            </strong>
                            <span
                              className="rca-bar-track"
                              role="img"
                              aria-label={`${j.job_name} 경과시간 ${j.elapsed_seconds}초`}
                            >
                              <span
                                style={{
                                  width: `${(Number(j.elapsed_seconds) / maxElapsed) * 100}%`,
                                }}
                              />
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </section>
        );
      })}
    </div>
  );
}
