import { useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { obj, rows, str, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';
import { metricName, metricTarget, metricUnit, metricValue } from '../lib/report';

const field = (metric: Row) => str(metric.id).split('.')[1];
const period = (metric: Row) => {
  const p = obj(metric.period);
  return p.at ? formatDate(str(p.at)) : `${formatDate(str(p.start))} ~ ${formatDate(str(p.end))}`;
};

function MetricsTable({ metrics, empty }: { metrics: Row[]; empty: string }) {
  if (!metrics.length) return <p>{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>항목</th>
            <th>대상</th>
            <th>값</th>
            <th>기록/분석 시각 (한국 시간)</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={str(m.id)}>
              <td>{metricName(str(m.id))}</td>
              <td>{metricTarget(m)}</td>
              <td>
                {metricValue(m)} {m.value == null ? '' : metricUnit(m)}
              </td>
              <td>{period(m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BasicReport({ topics }: { topics: Row[] }) {
  const [selected, setSelected] = useState('');
  const namespace = rows(topics.find((t) => t.topic_id === 'O08')?.metrics);
  const hourly = namespace.filter((m) => field(m) === 'hourly_gpu_activity');
  const targets = [...new Set(hourly.map((m) => metricTarget(m)))];
  const active = targets.includes(selected) ? selected : targets[0];
  const activity = hourly.filter((m) => metricTarget(m) === active);
  const graph = activity.map((m) => ({
    time: formatDate(str(obj(m.period).start)),
    activity: m.value,
  }));
  const nsTarget = activity[0] ? obj(activity[0].target) : {};
  const sameNamespace = (m: Row) =>
    obj(m.target).cluster_id === nsTarget.cluster_id &&
    obj(m.target).namespace === nsTarget.namespace;
  const peaks = namespace.filter((m) => field(m) === 'hourly_peak_gpu_count' && sameNamespace(m));
  const lows = namespace.filter(
    (m) =>
      field(m) === 'observed_low_activity_seconds' &&
      sameNamespace(m) &&
      obj(m.target).model === nsTarget.model,
  );
  const equipment = rows(topics.find((t) => t.topic_id === 'O01')?.metrics).filter(
    (m) => field(m).startsWith('recorded_') || field(m) === 'node_condition_seconds',
  );
  const monitoring = rows(topics.find((t) => t.topic_id === 'O11')?.metrics).filter(
    (m) => field(m).startsWith('target_') || field(m).startsWith('scrape_duration_'),
  );
  return (
    <>
      {topics.some((t) => t.topic_id === 'O08') && (
        <section className="result-section basic-report-activity">
          <h3>Namespace별 GPU 활동</h3>
          <p>
            같은 모델의 유효 관측만 평균에 사용합니다. 빈 구간은 0%가 아닙니다. 연결된 GPU의
            활동이며 Namespace의 독점 사용량은 아닙니다.
          </p>
          {!targets.length ? (
            <p>Namespace·GPU 연결과 활동 자료가 부족해 시간별 분석을 만들지 못했습니다.</p>
          ) : (
            <>
              <label className="field">
                클러스터 · Namespace · GPU 모델
                <select value={active} onChange={(e) => setSelected(e.target.value)}>
                  {targets.map((target) => (
                    <option key={target}>{target}</option>
                  ))}
                </select>
              </label>
              <MetricsTable
                metrics={namespace.filter(
                  (m) =>
                    field(m) === 'model_gpu_activity' &&
                    sameNamespace(m) &&
                    obj(m.target).model === nsTarget.model,
                )}
                empty="기간 평균을 계산할 수 없습니다."
              />
              <h4>시간대별 평균 활동률</h4>
              <div
                className="basic-report-chart"
                role="img"
                aria-label="시간대별 GPU 활동률 그래프. 아래 표에서 정확한 값과 GPU 대수를 확인할 수 있습니다."
              >
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={graph} margin={{ top: 16, right: 24, left: 0, bottom: 16 }}>
                    <XAxis dataKey="time" tick={{ fontSize: 12 }} minTickGap={50} />
                    <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Line
                      dataKey="activity"
                      name="평균 활동률 (%)"
                      stroke="var(--primary, #166e57)"
                      strokeWidth={2}
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <details>
                <summary>시간별 대수·활동률 표 · {activity.length}개 구간</summary>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>시간대 (한국 시간)</th>
                        <th>Namespace 전체 최대 동시 GPU</th>
                        <th>평균 활동률</th>
                        <th>평균에 사용한 GPU·분</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activity.map((m) => {
                        const peak = peaks.find((p) => obj(p.period).start === obj(m.period).start);
                        return (
                          <tr key={str(m.id)}>
                            <td>{period(m)}</td>
                            <td>{peak ? metricValue(peak) : '산출 불가'}</td>
                            <td>
                              {metricValue(m)}
                              {m.value == null ? '' : '%'}
                            </td>
                            <td>
                              {(Number(obj(m.denominator).value || 0) / 60).toLocaleString(
                                'ko-KR',
                                { maximumFractionDigits: 1 },
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </details>
              <h4>지속적으로 활동이 낮았던 구간</h4>
              <p>
                GPU별 5% 미만이 30분 이상 이어진 구간입니다. 미관측·Namespace 변경 구간은 이어
                붙이지 않습니다. 낭비나 회수 가능 여부는 별도 판단이 필요합니다.
              </p>
              <MetricsTable
                metrics={lows}
                empty={
                  activity.some((m) => m.value != null)
                    ? '유효 관측에서 조건에 맞는 구간을 찾지 못했습니다. 미관측 구간은 판단하지 않습니다.'
                    : '활동 자료가 없어 저활동 여부를 판단할 수 없습니다.'
                }
              />
            </>
          )}
        </section>
      )}
      {topics.some((t) => t.topic_id === 'O01') && (
        <section className="result-section">
          <h3>GPU·Node 관측 현황</h3>
          <p>
            아래 값은 분석 기간의 마지막 기록입니다. 실제 측정 시각이 확인되지 않은 Fleet 기록을
            현재 값이나 기간 평균으로 해석하지 마세요. Node 조건은 관측된 지속 시간이며 GPU 정상
            여부와는 다릅니다. 유효한 평균은 주제별 상세 수치에서 확인합니다.
          </p>
          <MetricsTable
            metrics={equipment}
            empty="표시할 장비 기록이 없습니다. 주제별 상세 수치와 자료 부족 사유를 확인하세요."
          />
        </section>
      )}
      {topics.some((t) => t.topic_id === 'O11') && (
        <section className="result-section">
          <h3>모니터링 수집 상태</h3>
          <p>
            관측된 수집 대상별 정상·실패·미관측 시간입니다. 전체 장비의 정상 여부나 전체 수집률을
            뜻하지 않습니다. 이번 보고서 조회의 실패 내역은 수집 진단에서 확인합니다.
          </p>
          <MetricsTable
            metrics={monitoring}
            empty="수집 대상의 응답 상태·지연 자료가 없어 판단할 수 없습니다."
          />
        </section>
      )}
    </>
  );
}
