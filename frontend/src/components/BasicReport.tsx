import { useState } from 'react';
import {
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';
import { metricName, metricTarget, metricUnit, metricValue } from '../lib/report';

const field = (metric: Row) => str(metric.id).split('.')[1];
const period = (metric: Row) => {
  const p = obj(metric.period);
  return p.at ? formatDate(str(p.at)) : `${formatDate(str(p.start))} ~ ${formatDate(str(p.end))}`;
};

export function operationalFindings(topics: Row[]) {
  return topics
    .flatMap((topic) =>
      rows(topic.findings)
        .filter((finding) => typeof finding.next_check === 'string' && !!str(finding.text))
        .map((finding): Row => ({ ...finding, topic_id: topic.topic_id })),
    )
    .sort(
      (a, b) =>
        Number(a.priority ?? 99) - Number(b.priority ?? 99) ||
        (str(a.id) < str(b.id) ? -1 : str(a.id) > str(b.id) ? 1 : 0),
    );
}

export function ReportChecks({
  topics,
  onEvidence,
}: {
  topics: Row[];
  onEvidence?: (id: string) => void;
}) {
  const findings = operationalFindings(topics);
  if (!findings.length) return null;
  const renderFinding = (finding: Row) => (
    <li key={str(finding.id)}>
      <p className="report-check-observation">{str(finding.text)}</p>
      <p className="report-check-next">
        <strong>다음 확인</strong> {str(finding.next_check)}
      </p>
      <div className="report-check-context">
        <span>{metricTarget(finding)}</span>
        {Object.keys(obj(finding.period)).length > 0 && <span>{period(finding)} · 한국 시간</span>}
      </div>
      <details>
        <summary>판단 근거 확인</summary>
        <div className="report-check-links">
          <a
            href={
              ['O01', 'O05', 'O08', 'O11'].includes(str(finding.topic_id))
                ? `#report-area-${str(finding.topic_id)}`
                : `#topic-${str(finding.topic_id)}`
            }
          >
            관련 분석 보기
          </a>
          {str(finding.incident_id) && (
            <a href={`/incidents/${encodeURIComponent(str(finding.incident_id))}`}>
              사건·조사 상세
            </a>
          )}
          {onEvidence &&
            strings(finding.evidence_refs).map((id, index) => (
              <button type="button" className="text-link" key={id} onClick={() => onEvidence(id)}>
                근거 {index + 1}
              </button>
            ))}
        </div>
      </details>
    </li>
  );
  return (
    <section className="result-section report-checks" aria-labelledby="report-checks-title">
      <h3 id="report-checks-title">먼저 확인할 내용</h3>
      <p>관측 근거에서 찾은 확인 대상입니다. 우선순위 순으로 읽고 대상·시간대를 확인하세요.</p>
      <ol>{findings.slice(0, 5).map(renderFinding)}</ol>
      {findings.length > 5 && (
        <details className="report-more-checks">
          <summary>나머지 확인 사항 {findings.length - 5}개</summary>
          <ol start={6}>{findings.slice(5).map(renderFinding)}</ol>
        </details>
      )}
    </section>
  );
}

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

// Merge only already calculated low-activity intervals for shading, never hourly averages.
export function lowActivityBands(metrics: Row[]) {
  const ranges = metrics
    .filter((m) => typeof m.value === 'number' && m.value > 0)
    .map((m) => ({
      start: Date.parse(str(obj(m.period).start)),
      end: Date.parse(str(obj(m.period).end)),
    }))
    .filter((p) => Number.isFinite(p.start) && Number.isFinite(p.end) && p.start < p.end)
    .sort((a, b) => a.start - b.start);
  const bands: { start: number; end: number }[] = [];
  for (const range of ranges) {
    const last = bands.at(-1);
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else bands.push({ ...range });
  }
  return bands;
}

export function BasicReport({ topics }: { topics: Row[] }) {
  const [selected, setSelected] = useState('');
  const namespace = rows(topics.find((t) => t.topic_id === 'O08')?.metrics);
  const hourly = namespace.filter((m) => field(m) === 'hourly_gpu_activity');
  const targets = [...new Set(hourly.map((m) => metricTarget(m)))];
  const priorityTarget = operationalFindings(topics.filter((topic) => topic.topic_id === 'O08'))
    .filter((finding) => ['activity_gap', 'low_activity'].includes(str(finding.category)))
    .map(metricTarget)
    .find((target) => targets.includes(target));
  const active = targets.includes(selected) ? selected : priorityTarget || targets[0];
  const activity = hourly
    .filter((m) => metricTarget(m) === active)
    .sort((a, b) => Date.parse(str(obj(a.period).start)) - Date.parse(str(obj(b.period).start)));
  const graph = activity.map((m) => ({
    time: Date.parse(str(obj(m.period).start)),
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
  const bands = lowActivityBands(lows);
  const graphEnd = activity.length ? Date.parse(str(obj(activity.at(-1)?.period).end)) : 0;
  const equipmentTopic = topics.find((t) => t.topic_id === 'O01');
  const equipment = rows(equipmentTopic?.metrics).filter(
    (m) => field(m).startsWith('recorded_') || field(m) === 'node_condition_seconds',
  );
  const equipmentChecks = operationalFindings(equipmentTopic ? [equipmentTopic] : []);
  const equipmentById = new Map(equipment.map((metric) => [str(metric.id), metric]));
  const focusedEquipment = [
    ...new Set(equipmentChecks.flatMap((finding) => strings(finding.value_refs))),
  ].flatMap((id) => (equipmentById.has(id) ? [equipmentById.get(id)!] : []));
  const incidents = operationalFindings(topics.filter((t) => t.topic_id === 'O05')).filter((f) =>
    str(f.incident_id),
  );
  const monitoring = rows(topics.find((t) => t.topic_id === 'O11')?.metrics).filter(
    (m) => field(m).startsWith('target_') || field(m).startsWith('scrape_duration_'),
  );
  return (
    <>
      {topics.some((t) => t.topic_id === 'O08') && (
        <section className="result-section basic-report-activity" id="report-area-O08">
          <h3>GPU 사용 패턴</h3>
          <p>
            Namespace별 GPU 활동과 저활동 시간대를 함께 봅니다. 같은 모델의 유효 관측만 평균에
            사용하며 빈 구간은 0%가 아닙니다. 연결된 GPU의 활동이며 Namespace의 독점 사용량은
            아닙니다.
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
              <h4>시간대별 활동률과 저활동 구간</h4>
              <p className="report-chart-key">
                <span aria-hidden="true" />
                음영: 선택한 모델의 GPU 중 연속 저활동이 관측된 구간 · Namespace 전체의 저활동을
                뜻하지 않습니다.
              </p>
              <div
                className="basic-report-chart"
                role="img"
                aria-label={`시간대별 GPU 활동률 그래프. GPU별 저활동 구간 ${lows.length}건을 음영으로 표시합니다. 아래 표에서 정확한 값과 GPU 대수를 확인할 수 있습니다.`}
              >
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={graph} margin={{ top: 16, right: 24, left: 0, bottom: 16 }}>
                    <XAxis
                      dataKey="time"
                      type="number"
                      domain={[graph[0]?.time ?? 0, graphEnd]}
                      tickFormatter={(time: number) => formatDate(new Date(time).toISOString())}
                      tick={{ fontSize: 12 }}
                      minTickGap={50}
                    />
                    <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
                    <Tooltip
                      labelFormatter={(time) => formatDate(new Date(Number(time)).toISOString())}
                    />
                    {bands.map((band) => (
                      <ReferenceArea
                        key={band.start}
                        x1={band.start}
                        x2={band.end}
                        y1={0}
                        y2={100}
                        fill="var(--report-low-activity)"
                        fillOpacity={0.45}
                        strokeOpacity={0}
                      />
                    ))}
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
              <p>
                GPU별 5% 미만이 30분 이상 이어진 구간만 표시합니다. 미관측·Namespace 변경 구간은
                이어 붙이지 않습니다. 저활동만으로 낭비나 회수 가능 여부를 판단하지 않습니다.
              </p>
              {lows.length === 0 && (
                <p>
                  {activity.some((m) => m.value != null)
                    ? '유효 관측에서 조건에 맞는 구간을 찾지 못했습니다. 미관측 구간은 판단하지 않습니다.'
                    : '활동 자료가 없어 저활동 여부를 판단할 수 없습니다.'}
                </p>
              )}
              {lows.length > 0 && (
                <details>
                  <summary>저활동 대상·정확한 시간 확인 · {lows.length}개 구간</summary>
                  <MetricsTable metrics={lows} empty="저활동 자료가 없습니다." />
                </details>
              )}
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
            </>
          )}
        </section>
      )}
      {equipmentTopic && (
        <section className="result-section" id="report-area-O01">
          <h3>장비·Node 점검 대상</h3>
          <p>
            위 확인 사항에 연결된 관측을 최대 12개 먼저 보여줍니다. 아래 기록값은 분석 기간의 마지막
            기록입니다. 실제 측정 시각이 확인되지 않은 Fleet 기록을 현재 값이나 기간 평균으로
            해석하지 마세요. Node 조건은 관측된 지속 시간이며 GPU 정상 여부와는 다릅니다.
          </p>
          {equipmentChecks.length > 0 ? (
            <>
              <MetricsTable
                metrics={focusedEquipment.slice(0, 12)}
                empty="수치로 확인할 근거가 부족합니다. 먼저 확인할 내용과 자료 부족 사유를 확인하세요."
              />
              <details>
                <summary>전체 장비 관측 수치 · {equipment.length}개</summary>
                <MetricsTable metrics={equipment} empty="표시할 장비 기록이 없습니다." />
              </details>
            </>
          ) : (
            <MetricsTable
              metrics={equipment}
              empty="표시할 장비 기록이 없습니다. 주제별 상세 수치와 자료 부족 사유를 확인하세요."
            />
          )}
        </section>
      )}
      {topics.some((t) => t.topic_id === 'O05') && (
        <section className="result-section" id="report-area-O05">
          <h3>장애·조사·처리 현황</h3>
          <p>
            분석 기간에 발생한 사건의 저장 상태입니다. 알람 해제·RCA 조사 완료·실제 조치 수행은 서로
            다릅니다. 상태는 자료 기준 시각의 기록이며 실시간 상태가 아닙니다.
          </p>
          {incidents.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>사건</th>
                    <th>알람 기록</th>
                    <th>공개 RCA</th>
                    <th>처리 확인</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((finding) => (
                    <tr key={str(finding.id)}>
                      <td>
                        <a href={`/incidents/${encodeURIComponent(str(finding.incident_id))}`}>
                          {metricTarget(finding)} · 사건 상세
                        </a>
                      </td>
                      <td>
                        {(
                          { firing: '발생 알림 수신', resolved: '해제 알림 수신' } as Record<
                            string,
                            string
                          >
                        )[str(finding.alarm_status)] || '미확인'}
                        {str(finding.status_as_of) && (
                          <p className="muted">{formatDate(str(finding.status_as_of))} 기준</p>
                        )}
                      </td>
                      <td>
                        {strings(finding.rca_result_ids).length > 0
                          ? `${strings(finding.rca_result_ids).length}건 연결됨`
                          : '연결된 결과 없음'}
                      </td>
                      <td>
                        {Array.isArray(finding.action_record_ids)
                          ? strings(finding.action_record_ids).length > 0
                            ? `연결된 조치 기록 ${strings(finding.action_record_ids).length}건 · 수행 내용 확인 필요`
                            : '연결된 조치 기록 없음 · 미수행 확정 아님'
                          : '조치 연결 기록 미확인'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>
              사건별 확인 기록이 없습니다. 주제별 상세 수치와 자료 부족 사유를 확인하세요. 기록
              부재를 장애 없음으로 해석하지 않습니다.
            </p>
          )}
          {topics.some((t) => t.topic_id === 'O06') && (
            <p id="report-area-O06">
              장애 당시 작업 연결을 추가했습니다. <a href="#topic-O06">확인된 GPU·작업 관계 보기</a>{' '}
              · 연결 관계만으로 피해나 원인을 단정하지 않습니다.
            </p>
          )}
        </section>
      )}
      {topics.some((t) => t.topic_id === 'O11') && (
        <section className="result-section" id="report-area-O11">
          <h3>자료 신뢰도</h3>
          <p>
            수집 실패·미관측 구간은 해당 시간대의 분석 판단을 제한합니다. 관측 대상의 수집 응답
            상태이며 전체 장비의 정상 여부나 전체 수집률을 뜻하지 않습니다.
          </p>
          <details>
            <summary>수집 대상별 응답·공백·지연 · {monitoring.length}개 수치</summary>
            <MetricsTable
              metrics={monitoring}
              empty="수집 대상의 응답 상태·지연 자료가 없어 판단할 수 없습니다."
            />
          </details>
        </section>
      )}
    </>
  );
}
