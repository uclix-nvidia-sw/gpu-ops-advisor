import { useState } from 'react';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { ReportPeriod } from './ReportMeta';
import { Badge, Notice, TextLink } from './ui';
import { reportRequestTime } from '../lib/reportPeriod';
import './aggregate-report.css';
import { NamespaceCharts } from './NamespaceCharts';

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
const namespaceKey = (row: Row) => JSON.stringify([row.cluster_id, row.namespace]);
export function namespaceGroups(comparisons: Row[]) {
  const groups = new Map<
    string,
    { key: string; cluster: string; namespace: string; models: Row[] }
  >();
  for (const row of comparisons) {
    if (!str(row.namespace)) continue;
    const key = namespaceKey(row);
    const group = groups.get(key) || {
      key,
      cluster: str(row.cluster_id),
      namespace: str(row.namespace),
      models: [],
    };
    group.models.push(row);
    groups.set(key, group);
  }
  return [...groups.values()];
}
function comparisonReason(row: Row) {
  if (row.comparison_status === 'comparable') return '동일 모델·완료 기간 비교';
  if (row.comparison_status === 'previous_not_observed') return '이전 기간 관측 없음';
  if (row.comparison_status === 'current_not_observed') return '현재 기간 관측 없음';
  if (row.previous_valid_hours != null)
    return `현재 ${row.valid_hours}/${row.expected_hours}시간 · 이전 ${row.previous_valid_hours}/${row.previous_expected_hours}시간 확인`;
  return '현재 또는 이전 기간 자료 부족';
}
function observedCount(models: Row[]) {
  const observed = models.filter((r) => r.observed_gpu_count != null);
  if (!observed.length) return '미확인';
  if (
    observed.some(
      (r) =>
        !rows(r.hours)
          .filter((h) => h.activity_percent != null)
          .flatMap((h) => strings(h.gpu_ids)).length,
    )
  )
    return '모델별 확인';
  const count = new Set(
    observed.flatMap((r) =>
      rows(r.hours)
        .filter((h) => h.activity_percent != null)
        .flatMap((h) => strings(h.gpu_ids)),
    ),
  ).size;
  return `${count}개${observed.length < models.length ? ' · 일부 확인' : ''}`;
}

export function namespaceActivity(models: Row[]) {
  const values = models
    .map((r) => r.activity_percent)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100);
  if (!values.length) return '산출 불가';
  const min = Math.min(...values),
    max = Math.max(...values);
  return min === max ? pct(min) : `${pct(min)}–${pct(max)}`;
}

export function incidentShortTitle(value: string) {
  const title = value.replace(/\s+/g, ' ').trim();
  if (!title) return '장애 설명 미저장 · 사건 상세 확인';
  if (/\bXID\s*79\b/i.test(title) && /fallen off.*bus/i.test(title))
    return 'XID 79 · GPU 연결 끊김 알림';
  if (/\bSXID\s*11001\b/i.test(title) && /ingress invalid command/i.test(title))
    return 'SXID 11001 · 스위치 수신 명령 오류 알림';
  const characters = Array.from(title);
  return characters.length > 60 ? `${characters.slice(0, 60).join('')}…` : title;
}

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
  const groups = namespaceGroups(comparisons);
  const selectedNodes = (models: Row[]) =>
    [...new Set(models.flatMap((r) => strings(r.nodes)))].sort();
  const unattributed = comparisons.filter((r) => !str(r.namespace));
  const [selection, setSelection] = useState('');
  const [modelSelection, setModelSelection] = useState('');
  const [incidentLimit, setIncidentLimit] = useState(50);
  const selected = groups.find((g) => g.key === selection) || groups[0];
  const models = selected?.models || [];
  const active =
    models.find((r) => keyOf(r) === modelSelection) ||
    models.find((r) => rows(r.hours).length) ||
    models[0];
  const hours = rows(active?.hours);
  const [hiddenNamespaces, setHiddenNamespaces] = useState<Set<string>>(() => new Set());
  const toggleNamespace = (key: string) =>
    setHiddenNamespaces((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const summary = obj(incident?.summary);
  return (
    <section id="final-report" className="aggregate-report" aria-label="운영 분석 보고서">
      <header className="aggregate-heading">
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
          <h2 id="namespace-summary-title">Namespace별 GPU 활동 현황</h2>
          <p>
            표는 전체 Namespace의 관측 구성을 보여줍니다. 그래프에서만 비교 대상을 선택할 수
            있습니다. 관측 GPU 수는 기간 내 확인된 고유 GPU 개수이며 서버 수나 동시 할당량이
            아닙니다.
          </p>
          {!groups.length ? (
            <Notice>
              선택한 기간에는 Namespace에 연결해 비교할 수 있는 자료가 없습니다. 새 작업을 오늘
              시작했다면 어제 보고서에는 포함되지 않습니다.
            </Notice>
          ) : (
            <>
              <div className="aggregate-table-scroll">
                <table className="aggregate-namespace-table">
                  <caption>클러스터·Namespace별 관측 구성</caption>
                  <thead>
                    <tr>
                      <th>클러스터 / Namespace</th>
                      <th>관측 노드</th>
                      <th>관측 GPU 수</th>
                      <th>평균 GPU 활동률</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((group) => {
                      return (
                        <tr key={group.key}>
                          <th scope="row">
                            <span>{group.cluster}</span>
                            {group.namespace}
                          </th>
                          <td>{selectedNodes(group.models).join(', ') || '미확인'}</td>
                          <td className="aggregate-number">{observedCount(group.models)}</td>
                          <td className="aggregate-number">
                            {namespaceActivity(group.models)}
                            {group.models.length > 1 && <small>모델별 평균 범위</small>}
                            {group.models.some((r) => r.quality_status !== 'ready') && (
                              <small>일부 자료 기준</small>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="aggregate-table-note">
                활동률은 확인된 자료의 평균입니다. 여러 GPU 모델을 사용하면 모델별 평균의 최소–최대
                범위를 표시합니다. 자료가 일부뿐이면 전체 기간의 사용 패턴으로 단정하지 않습니다.
              </p>
              <NamespaceCharts
                groups={groups}
                hidden={hiddenNamespaces}
                onToggle={toggleNamespace}
                onSetCluster={(keys, visible) =>
                  setHiddenNamespaces((previous) => {
                    const next = new Set(previous);
                    keys.forEach((key) => {
                      if (visible) next.delete(key);
                      else next.add(key);
                    });
                    return next;
                  })
                }
              />
              <details className="aggregate-model-detail">
                <summary>세부 수치와 자료 상태</summary>
                <label className="aggregate-detail-selector">
                  확인할 Namespace
                  <select
                    value={selected?.key || ''}
                    onChange={(event) => {
                      setSelection(event.target.value);
                      setModelSelection('');
                    }}
                  >
                    {groups.map((group) => (
                      <option key={group.key} value={group.key}>
                        {group.cluster} / {group.namespace}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  현재 자료가 충분해도 이전 기간에 공백이 있으면 증감 비교는 보류합니다. 다른 GPU
                  모델의 활동률을 하나의 평균으로 합치지 않습니다.
                </p>
                <div className="aggregate-table-scroll">
                  <table className="aggregate-model-table">
                    <thead>
                      <tr>
                        <th>GPU 모델 / 상세 선택</th>
                        <th>관측 GPU 수</th>
                        <th>현재 활동률</th>
                        <th>이전 활동률</th>
                        <th>변화</th>
                        <th>유효 시간대</th>
                      </tr>
                    </thead>
                    <tbody>
                      {models.map((row) => (
                        <tr key={keyOf(row)} className={row === active ? 'selected' : ''}>
                          <th scope="row">
                            <button
                              type="button"
                              aria-pressed={row === active}
                              onClick={() => setModelSelection(keyOf(row))}
                            >
                              {str(row.gpu_model) || '모델 미확인'}
                            </button>
                          </th>
                          <td className="aggregate-number">
                            {row.observed_gpu_count == null
                              ? '미확인'
                              : `${row.observed_gpu_count}개`}
                          </td>
                          <td className="aggregate-number">
                            {pct(row.activity_percent)}
                            {row.quality_status !== 'ready' && <small>확인된 시간대만</small>}
                          </td>
                          <td className="aggregate-number">{pct(row.previous_activity_percent)}</td>
                          <td>
                            {difference(row.change_percentage_points)}
                            <small>{comparisonReason(row)}</small>
                          </td>
                          <td className="aggregate-number">
                            {String(row.valid_hours)} / {String(row.expected_hours)}시간
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="aggregate-hour-detail">
                  <h4>선택한 모델의 시간대별 수치</h4>
                  <p>
                    {str(active?.cluster_id)} / {str(active?.namespace)} / {str(active?.gpu_model)}
                  </p>
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
                {active && (
                  <div className="aggregate-patterns">
                    <h4>사용 패턴 요약</h4>
                    {rows(usage.findings)
                      .filter(
                        (f) =>
                          str(obj(f.target).cluster_id) === str(active.cluster_id) &&
                          str(obj(f.target).namespace) === str(active.namespace) &&
                          str(obj(f.target).model) === str(active.gpu_model),
                      )
                      .map((f) => (
                        <p key={str(f.id)}>{str(f.text)}</p>
                      ))}
                  </div>
                )}
              </details>
            </>
          )}
          {unattributed.length > 0 && (
            <details className="aggregate-unattributed">
              <summary>Namespace에 연결하지 못한 관측 · {unattributed.length}개 모델 묶음</summary>
              <p>
                이 자료는 Namespace별 사용량 비교에서 제외했습니다. 미사용 GPU라고 판단한 것은
                아닙니다.
              </p>
              <ul>
                {unattributed.map((row) => (
                  <li key={keyOf(row)}>
                    {str(row.cluster_id)} · {str(row.gpu_model)}:{' '}
                    {Array.from(new Set(rows(row.hours).flatMap((h) => strings(h.reasons))))
                      .map((r) => aggregateReasons[r] || r)
                      .join(' · ') || 'Namespace 식별 정보 부족'}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
      {incident && (
        <section aria-labelledby="incident-summary-title">
          <h2 id="incident-summary-title">기간 내 장애 알림 현황</h2>
          {rows(incident.findings).map((f) => (
            <p key={str(f.id)}>{str(f.text)}</p>
          ))}
          {rows(summary.categories).length > 0 && (
            <div className="aggregate-table-scroll">
              <table className="aggregate-incident-types">
                <caption>장애 종류별 발생 현황 · 동일 원인을 의미하지 않습니다</caption>
                <thead>
                  <tr>
                    <th>클러스터 / 장애 종류</th>
                    <th>발생 노드</th>
                    <th>이번 기간</th>
                    <th>이전 기간</th>
                    <th>작성 시 발생 중</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(summary.categories).map((category) => (
                    <tr key={`${category.cluster_id}/${category.name}`}>
                      <th scope="row">
                        <span>{str(category.cluster_id)}</span>
                        {str(category.name)}
                      </th>
                      <td>{strings(category.nodes).join(', ') || '노드 미확인'}</td>
                      <td className="aggregate-number">
                        {String(category.count)}건
                        {Number(category.test_count) > 0 && (
                          <small>시험 표시 {String(category.test_count)}건 포함</small>
                        )}
                      </td>
                      <td className="aggregate-number">{String(category.previous_count)}건</td>
                      <td className="aggregate-number">{String(category.firing_count)}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Number(summary.unclassified_count) > 0 && (
            <p className="aggregate-data-note">
              장비·증상 식별이 부족한 {String(summary.unclassified_count)}건은 같은 GPU의 반복
              장애인지 확인할 수 없습니다. 미확인 사건은 반복 그룹 수에 포함되지 않습니다.
            </p>
          )}
          {rows(summary.incidents).some((row) => !str(row.symptom)) && (
            <Notice>
              이 보고서에 장애 설명이 저장되지 않은 사건이 있습니다. 사건 상세에서 원문을
              확인하세요. 이 화면에서는 누락된 내용을 추가로 조회하거나 추정하지 않습니다.
            </Notice>
          )}

          {summary.count === 0 ? (
            <Notice>
              선택한 범위·기간에 저장된 사건이 없습니다. 장비 전체의 무장애를 뜻하지 않습니다.
            </Notice>
          ) : (
            rows(summary.incidents).length > 0 && (
              <div>
                <p className="aggregate-data-note">
                  알림 상태는 보고서 작성 중 조회한 당시 기준이며, 현재 상태와 다를 수 있습니다.
                  <br />
                  기준 시각:{' '}
                  {str(summary.status_as_of)
                    ? `${reportRequestTime(str(summary.status_as_of))} KST`
                    : '미저장'}
                </p>
                <div className="aggregate-table-scroll">
                  <table className="aggregate-incident-table">
                    <caption>사건별 알림 내용</caption>
                    <thead>
                      <tr>
                        <th>발생 시각</th>
                        <th>클러스터</th>
                        <th>노드</th>
                        <th>알림 내용</th>
                        <th>
                          알림 상태<span>작성 기준</span>
                        </th>
                        <th>상세 보기</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows(summary.incidents)
                        .slice(0, incidentLimit)
                        .map((row) => (
                          <tr key={str(row.id)}>
                            <td className="aggregate-date">
                              <time dateTime={str(row.occurred_at)}>
                                {reportRequestTime(str(row.occurred_at))
                                  .split(/ (?=\d{2}:\d{2}:\d{2}$)/)
                                  .map((part, index) => (
                                    <span key={index}>{part}</span>
                                  ))}
                              </time>
                            </td>
                            <td>{str(row.cluster_id) || '미확인'}</td>
                            <td>{str(obj(row.target).node) || '미확인'}</td>
                            <td>
                              <span className="aggregate-alert-title">
                                {incidentShortTitle(str(row.symptom))}
                              </span>
                              {obj(row.target).test_alarm === true && (
                                <small>시험 알림으로 표시됨</small>
                              )}
                            </td>
                            <td>
                              {row.alarm_status === 'firing' ? (
                                <Badge status="firing" label="발생 중" />
                              ) : (
                                <span>{row.alarm_status === 'resolved' ? '해제' : '미확인'}</span>
                              )}
                            </td>
                            <td>
                              <TextLink to={`/incidents/${encodeURIComponent(str(row.id))}`}>
                                {row.result_id ? 'RCA 보기' : '사건 보기'}
                              </TextLink>
                              {!row.result_id && <small>RCA 미발행</small>}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
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
              <summary>같은 GPU·동일 증상의 반복 비교</summary>
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
