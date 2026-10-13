import { useState } from 'react';
import { Link } from 'react-router-dom';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { ReportPeriod } from './ReportMeta';
import { Notice } from './ui';
import { reportRequestTime } from '../lib/reportPeriod';
import './aggregate-report.css';

export const aggregateReasons: Record<string, string> = {
  unobserved_hour: '이 시간대 관측 없음',
  identity_labels_missing: 'GPU·Namespace·Pod 식별 정보 부족',
  identity_labels_conflict: 'GPU·노드 식별 정보 불일치',
  duplicate_or_changed_gpu_identity: 'GPU 연결 변경 또는 중복 관측',
  invalid_activity_aggregate: '활동률 집계 검증 실패',
  pod_identity_unverified: 'Pod 신원 확인 불가',
  incomplete_hour_or_sampling_interval: '시간대 관측 부족 또는 수집 주기 불일치',
  node_sharing_configuration_unverified: 'GPU 공유 설정 이력 미확인',
  shared_or_mig_attribution_unverified: '공유 GPU·MIG 귀속 미확인',
  report_query_failed: '집계 조회 실패',
  report_datasource_unavailable: '자료 조회 경로 미확인',
  namespace_observations_missing: 'Namespace 관측 자료 없음',
  incident_limit_exceeded: '사건 조회 상한 초과',
  query_unavailable: '집계 조회 불가',
  report_response_limit_exceeded: '조회 자료 크기 상한 초과',
  report_point_limit_exceeded: '조회 표본 수 상한 초과',
  report_query_limit_exceeded: '조회 횟수 상한 초과',
  invalid_prometheus_matrix: '집계 응답 형식 오류',
  partial_or_invalid_prometheus_response: '불완전한 집계 응답',
};
const pct = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '산출 불가';
const difference = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%p`
    : '비교 보류';
const keyOf = (row: Row) => [row.cluster_id, row.namespace, row.gpu_model].join('/');

export function AggregateReport({
  value,
  onEvidence,
}: {
  value: Row;
  onEvidence: (id: string) => void;
}) {
  const topics = rows(value.topics);
  const usage = topics.find((t) => t.topic_id === 'namespace_usage');
  const incident = topics.find((t) => t.topic_id === 'incident_summary');
  const comparisons = rows(usage?.rows);
  const [selection, setSelection] = useState('');
  const [incidentLimit, setIncidentLimit] = useState(50);
  const active =
    comparisons.find((r) => keyOf(r) === selection) ||
    comparisons.find((r) => str(r.namespace) && rows(r.hours).length) ||
    comparisons[0];
  const hours = rows(active?.hours);
  const points = hours.map((h, i) => ({
    x: 44 + (i * 892) / Math.max(1, hours.length - 1),
    y: typeof h.activity_percent === 'number' ? 220 - h.activity_percent * 1.8 : null,
  }));
  const line = points
    .map((p, i) =>
      p.y === null ? '' : `${i === 0 || points[i - 1].y === null ? 'M' : 'L'}${p.x},${p.y}`,
    )
    .join(' ');
  const summary = obj(incident?.summary);
  return (
    <section id="final-report" className="aggregate-report" aria-label="운영 분석 보고서">
      <header className="aggregate-heading">
        <h2>Namespace 활동과 운영 변화</h2>
        <ReportPeriod value={value.time_range} />
        <p>직전 같은 길이의 기간과 비교합니다. 모든 시각은 한국 시간 기준입니다.</p>
      </header>
      <Notice>
        활동률은 연결 GPU의 관측 표본 평균입니다. 부서의 독점 사용량·할당 효율이나 GPU 회수 가능량을
        뜻하지 않습니다.
      </Notice>
      {rows(value.narrative).length > 0 && (
        <section aria-label="주요 변화 요약">
          <h3>주요 변화 요약</h3>
          {rows(value.narrative)
            .slice(0, 3)
            .map((finding) => (
              <p key={str(finding.id)}>{str(finding.summary_text, str(finding.text))}</p>
            ))}
        </section>
      )}
      {usage && (
        <section aria-labelledby="namespace-summary-title">
          <h3 id="namespace-summary-title">Namespace별 비교</h3>
          <p>
            같은 GPU 모델 안에서 활동 수준을 비교하세요. 행을 선택하면 시간대별 변화와 자료 부족
            사유를 볼 수 있습니다.
          </p>
          {!comparisons.length ? (
            <Notice>Namespace 집계 자료가 없습니다. 조회 상태와 수집 경로를 확인해 주세요.</Notice>
          ) : (
            <>
              <div className="aggregate-table-scroll">
                <table>
                  <caption>클러스터·Namespace·GPU 모델별 관측 비교</caption>
                  <thead>
                    <tr>
                      <th>클러스터 / Namespace</th>
                      <th>GPU 모델</th>
                      <th>관측 GPU</th>
                      <th>평균 활동률</th>
                      <th>이전 기간</th>
                      <th>변화</th>
                      <th>유효 시간대</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisons.map((row) => (
                      <tr key={keyOf(row)} className={row === active ? 'selected' : ''}>
                        <th scope="row">
                          <span>{str(row.cluster_id)}</span>
                          <button
                            type="button"
                            aria-pressed={row === active}
                            onClick={() => setSelection(keyOf(row))}
                          >
                            {str(row.namespace) || 'Namespace 미표기'}
                          </button>
                        </th>
                        <td>{str(row.gpu_model) || '미확인'}</td>
                        <td>
                          {row.observed_gpu_count == null
                            ? '미확인'
                            : `${row.observed_gpu_count}대`}
                        </td>
                        <td>{pct(row.activity_percent)}</td>
                        <td>{pct(row.previous_activity_percent)}</td>
                        <td>
                          {difference(row.change_percentage_points)}
                          {row.comparison_status === 'previous_not_observed' && (
                            <small>이전 관측 없음</small>
                          )}
                          {row.comparison_status === 'current_not_observed' && (
                            <small>현재 관측 없음</small>
                          )}
                        </td>
                        <td>
                          {String(row.valid_hours)} / {String(row.expected_hours)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="aggregate-chart">
                <h4>
                  {str(active?.cluster_id)} · {str(active?.namespace) || 'Namespace 미표기'}
                </h4>
                <p>
                  {str(active?.gpu_model)} · 시간대별 평균 활동률 · 빈 구간은 0%가 아닌 산출
                  불가입니다.
                </p>
                {hours.length ? (
                  <svg
                    viewBox="0 0 960 270"
                    role="img"
                    aria-label={`${str(active?.namespace)} 시간대별 GPU 활동률. 상세 수치는 아래 표에서 확인할 수 있습니다.`}
                  >
                    {[0, 50, 100].map((n) => (
                      <g key={n}>
                        <line
                          x1="44"
                          x2="936"
                          y1={220 - n * 1.8}
                          y2={220 - n * 1.8}
                          className="aggregate-grid"
                        />
                        <text x="2" y={224 - n * 1.8}>
                          {n}%
                        </text>
                      </g>
                    ))}
                    <path d={line} className="aggregate-activity-line" />
                    {points
                      .filter((p) => p.y !== null)
                      .map((p, i) => (
                        <circle
                          key={i}
                          cx={p.x}
                          cy={p.y!}
                          r="2.5"
                          className="aggregate-activity-dot"
                        />
                      ))}
                    <text x="44" y="250">
                      {reportRequestTime(str(hours[0]?.start)).slice(0, -3)}
                    </text>
                    <text x="936" y="250" textAnchor="end">
                      {reportRequestTime(str(hours.at(-1)?.end)).slice(0, -3)}
                    </text>
                  </svg>
                ) : (
                  <Notice>현재 기간의 시간대별 자료가 없습니다.</Notice>
                )}
                <p>
                  {active?.low_activity_hours == null
                    ? '자료가 부족해 낮은 활동 시간대 수는 판단을 보류합니다.'
                    : `평균 활동률 5% 미만: ${active.low_activity_hours}개 시간대. 이 기준은 보고서 분류 기준이며 운영정책이 아닙니다.`}
                </p>
                <details>
                  <summary>시간대별 수치와 자료 부족 사유</summary>
                  <div className="aggregate-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>시간대 시작</th>
                          <th>평균 활동률</th>
                          <th>자료 상태</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hours.map((h) => (
                          <tr key={str(h.end)}>
                            <td>{reportRequestTime(str(h.start))}</td>
                            <td>{pct(h.activity_percent)}</td>
                            <td>
                              {strings(h.reasons)
                                .map((r) => aggregateReasons[r] || r)
                                .join(' · ') || '관측 조건 확인'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </div>
            </>
          )}
          <div className="aggregate-patterns">
            <h4>사용 패턴 요약</h4>
            {rows(usage.findings)
              .filter(
                (f) =>
                  !active ||
                  (str(obj(f.target).cluster_id) === str(active.cluster_id) &&
                    str(obj(f.target).namespace) === str(active.namespace) &&
                    str(obj(f.target).model) === str(active.gpu_model)),
              )
              .map((f) => (
                <p key={str(f.id)}>{str(f.text)}</p>
              ))}
          </div>
        </section>
      )}
      {incident && (
        <section aria-labelledby="incident-summary-title">
          <h3 id="incident-summary-title">기간 내 사건과 반복 현황</h3>
          {rows(incident.findings).map((f) => (
            <p key={str(f.id)}>{str(f.text)}</p>
          ))}
          <p>알림 상태 조회 시점: {reportRequestTime(str(summary.status_as_of))}</p>
          {summary.count === 0 ? (
            <Notice>
              선택한 범위·기간에 저장된 사건이 없습니다. 장비 전체의 무장애를 뜻하지 않습니다.
            </Notice>
          ) : (
            rows(summary.incidents).length > 0 && (
              <div className="aggregate-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>발생 시각</th>
                      <th>클러스터 / 증상</th>
                      <th>알림 상태</th>
                      <th>기존 조사</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows(summary.incidents)
                      .slice(0, incidentLimit)
                      .map((row) => (
                        <tr key={str(row.id)}>
                          <td>{reportRequestTime(str(row.occurred_at))}</td>
                          <td>
                            <span>{str(row.cluster_id)}</span>
                            <Link to={`/incidents/${encodeURIComponent(str(row.id))}`}>
                              {str(row.symptom)}
                            </Link>
                          </td>
                          <td>
                            {row.alarm_status === 'resolved'
                              ? '해제'
                              : row.alarm_status === 'firing'
                                ? '발생 중'
                                : '미확인'}
                          </td>
                          <td>
                            {row.result_id ? (
                              <Link to={`/incidents/${encodeURIComponent(str(row.id))}`}>
                                공개 RCA 확인
                              </Link>
                            ) : (
                              '미발행'
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                {rows(summary.incidents).length > incidentLimit && (
                  <button
                    type="button"
                    className="button"
                    onClick={() => setIncidentLimit((n) => n + 50)}
                  >
                    사건 50건 더 보기 · 전체 {String(summary.count)}건
                  </button>
                )}
              </div>
            )
          )}
          {rows(summary.groups).length > 0 && (
            <details>
              <summary>같은 장비·증상의 반복 비교</summary>
              <table>
                <thead>
                  <tr>
                    <th>클러스터 / 장비 / 증상</th>
                    <th>이번 기간</th>
                    <th>이전 기간</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(summary.groups).map((g, i) => (
                    <tr key={i}>
                      <td>
                        {str(g.cluster_id)} · {str(g.gpu_uuid)} · {str(g.symptom)}
                      </td>
                      <td>{String(g.count)}건</td>
                      <td>{String(g.previous_count)}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                장비 식별자가 부족해 반복 분류에서 제외된 사건:{' '}
                {String(summary.unclassified_count || 0)}건
              </p>
            </details>
          )}
        </section>
      )}
      <details className="aggregate-evidence">
        <summary>집계 기준과 근거</summary>
        <p>
          일평균끼리 평균내지 않고 활동률 합계와 표본 수를 합산합니다. 이전 보고서의 시간가중 평균과
          계산 방식이 다릅니다.
        </p>
        {strings(value.limitations).map((text) => (
          <p key={text}>{text}</p>
        ))}
        <div className="aggregate-evidence-buttons">
          {strings(value.evidence_refs).map((id, i) => (
            <button key={id} className="button" onClick={() => onEvidence(id)}>
              집계 근거 {i + 1}
            </button>
          ))}
        </div>
      </details>
    </section>
  );
}
