import { obj, rows, str, strings } from '../lib/live';
import { formatDate } from '../lib/domain';
import {
  collectionStatus,
  groupLabel,
  namespaceRows,
  metricUnit,
  metricName,
  metricTarget,
  metricValue,
  reportObservations,
  reportReason,
  topicName,
} from '../lib/report';
import { Badge, Notice } from './ui';
import { DataView } from './live';
import { reportMetrics } from '../lib/workflow';
import { type Row } from '../lib/live';

export function ReportContent({
  value,
  request,
  onEvidence,
}: {
  value: unknown;
  request?: unknown;
  onEvidence: (id: string) => void;
}) {
  const result = obj(value),
    topics = rows(result.topics),
    observations = reportObservations(result);
  if (!Object.keys(result).length)
    return <p>아직 발행된 보고서가 없습니다. 작업 상태를 확인하세요.</p>;
  const metrics = reportMetrics(result);
  const known = metrics.filter((metric) => metric.value != null).length;
  const quality = obj(result.quality);
  const namespaceTopic = topics.find((topic) => topic.topic_id === 'O08');
  const namespaceQuality = obj(namespaceTopic?.quality);
  const namespaceMetrics = namespaceRows(rows(namespaceTopic?.metrics));
  const requestedGroups = quality.requested_group_by ?? obj(request).group_by;
  const requestedNamespace = strings(requestedGroups).includes('namespace');
  const appliedNamespace = strings(namespaceQuality.applied_group_by).includes('namespace');
  const collection = obj(quality.collection);
  const limited = observations.filter((o) =>
    strings(o.reasons).some(
      (reason) => reason.includes('budget_exhausted') || reason === 'discovery_deadline_exhausted',
    ),
  );
  const observed = metrics.find((m) =>
    ['observed_gpu_count', 'observed_devices'].includes(str(m.id).split('.')[1]),
  );
  const mapped = metrics.find((m) => str(m.id).split('.')[1] === 'mapped_gpu_count');
  return (
    <div className="stack">
      <section className="result-section">
        <h3>분석 요약</h3>
        <p className="report-version">데이터 기준 시각: {formatDate(str(result.data_cutoff_at))}</p>
        <p>
          {formatDate(str(obj(result.time_range).start))} –{' '}
          {formatDate(str(obj(result.time_range).end))} · {str(result.timezone, 'Asia/Seoul')}
        </p>
        <p>
          {rows(obj(result.scope).clusters)
            .map(
              (cluster) =>
                `${str(cluster.cluster_id).toUpperCase()} / ${cluster.namespaces == null ? '전체 Namespace' : strings(cluster.namespaces).join(', ')}`,
            )
            .join(' · ')}
        </p>
        <p>
          요청한 집계: {groupLabel(requestedGroups)} · 계산 기준:{' '}
          {str(obj(result.versions).criteria, '기록 없음')}
        </p>
        {(observed || mapped) && (
          <p>
            {observed && (
              <>
                관측된 GPU {metricValue(observed)}
                {metricUnit(observed)}.{' '}
              </>
            )}
            {mapped && (
              <>
                Pod 연결이 확인된 GPU {metricValue(mapped)}
                {metricUnit(mapped)}.
              </>
            )}{' '}
            연결이 확인되지 않은 GPU를 유휴 장비로 판단하지 않습니다.
          </p>
        )}
        <Notice>
          {known
            ? `${metrics.length}개 항목 중 ${known}개를 산출했습니다. 산출하지 못한 항목과 이유는 주제별로 표시합니다.`
            : '작업은 완료됐지만 계산 가능한 근거가 부족합니다. 수집 상태와 항목별 사유를 확인하세요.'}
        </Notice>
        {!!str(quality.narrative_reason) && (
          <p className="muted">
            {reportReason(str(quality.narrative_reason))} 계산된 수치는 유지합니다.
          </p>
        )}
        {result.narrative_status === 'omitted' && !quality.narrative_reason && (
          <p className="muted">
            AI 설명은 생성되지 않았습니다. 아래에는 원본 관측에 근거한 계산 결과만 표시합니다.
          </p>
        )}
        {str(result.summary) && <p>{str(result.summary)}</p>}
        {result.narrative_status === 'failed' && !quality.narrative_reason && (
          <p className="muted">
            AI 설명을 생성하지 못했습니다. 이 결과에는 구체적인 실패 이유가 기록되지 않았습니다.
            계산된 수치와 근거는 유지합니다.
          </p>
        )}
        {!!rows(result.narrative).length && (
          <ul>
            {rows(result.narrative).map((fact, index) => (
              <li key={str(fact.id, String(index))}>
                {strings(fact.value_refs)
                  .map((ref) => {
                    const metric = metrics.find((item) => item.id === ref);
                    return metric
                      ? `${metricName(ref)}: ${metricValue(metric)} ${metricUnit(metric)} (${metricTarget(metric)})`
                      : '';
                  })
                  .filter(Boolean)
                  .join(' · ') || str(fact.text)}
              </li>
            ))}
          </ul>
        )}
      </section>
      {!!limited.length && (
        <Notice tone="warning">
          실행 제한으로 {limited.length}개 조회 대상의 수집이 완료되지 않았습니다. 연결 장애나 해당
          기간 데이터 없음과 구분하세요.
          {typeof collection.query_calls === 'number' && (
            <>
              {' '}
              조회 호출 {collection.query_calls} / {String(collection.query_limit)}회.
            </>
          )}{' '}
          CPC·Namespace 범위 또는 분석 주제를 줄여 새 보고서를 요청할 수 있습니다.
        </Notice>
      )}
      {namespaceTopic && (
        <section className="result-section">
          <h3>Namespace GPU 현황</h3>
          <p>
            적용된 집계:{' '}
            {appliedNamespace
              ? groupLabel(namespaceQuality.applied_group_by)
              : '새 Namespace 활동률 집계 미적용'}
            .
          </p>
          {!appliedNamespace && (
            <Notice>
              {requestedNamespace
                ? 'Namespace 집계를 요청했지만 새 활동률 계산이 적용되지 않았습니다.'
                : '이 보고서에는 새 Namespace 활동률 집계가 적용되지 않았습니다.'}{' '}
              새 보고서에서 ‘Namespace GPU 현황’을 선택하세요. 계산 기준 1.2를 지원하는 서버가
              필요하며 저장된 결과는 바뀌지 않습니다.
            </Notice>
          )}
          <p>
            연결 GPU의 관측 활동이며 Namespace의 실제 소비량·독점 할당량은 아닙니다. 공유 구간은
            Namespace 사이에 중복될 수 있습니다.
          </p>
          {!!namespaceMetrics.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CPC</th>
                    <th>Namespace</th>
                    <th>연결 관측 시간</th>
                    <th>평균에 사용한 시간</th>
                    <th>연결 GPU 평균 활동률</th>
                    <th>제외·보류 사유</th>
                  </tr>
                </thead>
                <tbody>
                  {namespaceMetrics.map(({ target, metrics: values }) => (
                    <tr key={JSON.stringify(target)}>
                      <td>{str(target.cluster_id)}</td>
                      <td>{str(target.namespace)}</td>
                      {[
                        'observed_namespace_hours',
                        'namespace_activity_valid_hours',
                        'namespace_connected_gpu_util',
                      ].map((name) => (
                        <td key={name}>
                          {values[name]
                            ? `${metricValue(values[name])}${values[name].value == null ? '' : ` ${metricUnit(values[name])}`}`
                            : '미계산'}
                        </td>
                      ))}
                      <td>
                        {[
                          ...new Set(
                            Object.values(values).flatMap((m) => [
                              ...strings(obj(m.quality).excluded_reasons),
                              ...(m.value == null ? [str(obj(m.quality).reason)] : []),
                            ]),
                          ),
                        ]
                          .filter(Boolean)
                          .map(reportReason)
                          .join(' ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>Namespace에 연결할 수 있는 유효 관측이 없습니다. 아래 O08 산출 제한을 확인하세요.</p>
          )}
        </section>
      )}
      <details id="report-topic-details">
        <summary>주제별 상세 수치 · {topics.length}개 주제</summary>
        {topics.map((topic) => (
          <section
            className="result-section"
            id={`topic-${str(topic.topic_id)}`}
            key={str(topic.topic_id)}
          >
            <div className="head-actions report-topic-head">
              <h3>{topicName(str(topic.topic_id))}</h3>
              <Badge status={str(topic.status)} />
            </div>
            {(str(obj(topic.quality).interpretation) ||
              rows(topic.metrics).some((m) =>
                str(m.id).includes('namespace_connected_gpu_util'),
              )) && (
              <Notice tone="warning">
                {str(
                  obj(topic.quality).interpretation,
                  '연결 GPU의 활동률은 Namespace의 실사용률·독점 할당량이 아닙니다. 유효 관측 범위 안에서만 해석하세요.',
                )}
              </Notice>
            )}
            {(topic.topic_id === 'O08' || obj(topic.quality).requested_group_by != null) && (
              <p className="muted">
                요청 집계 축:{' '}
                {strings(obj(topic.quality).requested_group_by).join(', ') || '미확인'} / 적용 집계
                축: {strings(obj(topic.quality).applied_group_by).join(', ') || '미확인'} ·
                criteria가 다른 보고서의 수치를 동일 기준으로 비교하지 않습니다.
              </p>
            )}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>항목</th>
                    <th>대상</th>
                    <th>값</th>
                    <th>단위</th>
                    <th>산출 제한</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(topic.metrics).map((metric) => (
                    <tr key={str(metric.id)}>
                      <td>{metricName(str(metric.id))}</td>
                      <td>{metricTarget(metric)}</td>
                      <td>{metricValue(metric)}</td>
                      <td>{metricUnit(metric)}</td>
                      <td>
                        {metric.value == null ? reportReason(str(obj(metric.quality).reason)) : '—'}
                        {strings(obj(metric.quality).excluded_reasons).map((reason) => (
                          <p key={reason}>{reportReason(reason)}</p>
                        ))}
                        <details>
                          <summary>분모·산식·기간·근거</summary>
                          <DataView
                            value={{
                              denominator: metric.denominator,
                              method: metric.method,
                              period: metric.period,
                              quality: metric.quality,
                            }}
                          />
                          <div className="head-actions">
                            {strings(metric.evidence_refs).map((id) => (
                              <button key={id} className="text-link" onClick={() => onEvidence(id)}>
                                근거 {id}
                              </button>
                            ))}
                          </div>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!!strings(topic.missing_inputs).length && (
              <ul>
                {[...new Set(strings(topic.missing_inputs))].map((reason) => (
                  <li key={reason}>{reportReason(reason)}</li>
                ))}
              </ul>
            )}
            {!!rows(topic.facts).length && (
              <ReportStatements
                title="확인된 사실"
                items={rows(topic.facts)}
                metrics={metrics}
                onEvidence={onEvidence}
              />
            )}
            {!!rows(topic.findings).length && (
              <ReportStatements
                title="분석 판단"
                items={rows(topic.findings)}
                metrics={metrics}
                onEvidence={onEvidence}
              />
            )}
            {!!rows(topic.recommendations).length && (
              <ReportStatements
                title="검토 권고·보류"
                items={rows(topic.recommendations)}
                metrics={metrics}
                onEvidence={onEvidence}
                recommendation
              />
            )}
          </section>
        ))}
      </details>
      {!topics.length && metrics.length > 0 && (
        <section className="result-section">
          <h3>저장된 수치 · 이전 결과 형식</h3>
          <DataView value={metrics} />
        </section>
      )}
      {!!observations.length && (
        <section className="result-section">
          <h3>데이터 수집 상태</h3>
          <p className="muted">
            응답 표본 수는 조회 구간별 응답 건수의 합입니다. 경계 중복을 제거한 고유 표본 수 또는
            전체 관측률이 아닙니다.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>클러스터</th>
                  <th>조회 데이터</th>
                  <th>결과</th>
                  <th>수집 표본</th>
                  <th>사유</th>
                </tr>
              </thead>
              <tbody>
                {observations.map((observation) => (
                  <tr key={`${str(observation.query_id)}:${str(observation.cluster_id)}`}>
                    <td>{str(observation.cluster_id)}</td>
                    <td>
                      {str(observation.metric, str(observation.query_id))}
                      {observation.metric != null && (
                        <small className="muted"> · {str(observation.query_id)}</small>
                      )}
                    </td>
                    <td>{collectionStatus(observation)}</td>
                    <td>{String(observation.sample_count)}</td>
                    <td>{strings(observation.reasons).map(reportReason).join(' ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {!observations.length && (
        <p className="muted">세부 조회 결과는 아래 수집 근거에서 확인할 수 있습니다.</p>
      )}
      {!!strings(result.limitations).length && (
        <section className="result-section">
          <h3>해석 시 참고사항</h3>
          <ul>
            {strings(result.limitations).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      <details>
        <summary>수집 근거 · {strings(result.evidence_refs).length}건</summary>
        <div className="head-actions">
          {strings(result.evidence_refs).map((id, index) => (
            <button className="button" key={id} onClick={() => onEvidence(id)}>
              근거 {index + 1}
            </button>
          ))}
        </div>
      </details>
      <details>
        <summary>원본 결과 보기</summary>
        <DataView value={result} />
      </details>
    </div>
  );
}

function ReportStatements({
  title,
  items,
  metrics,
  onEvidence,
  recommendation = false,
}: {
  title: string;
  items: Row[];
  metrics: Row[];
  onEvidence: (id: string) => void;
  recommendation?: boolean;
}) {
  return (
    <div className="report-statements">
      <h4>{title}</h4>
      {items.map((item, index) => (
        <article key={str(item.id, String(index))} className="report-statement">
          {recommendation && (
            <div className="head-actions">
              <Badge
                status={item.eligibility === 'eligible' ? 'partial' : 'blocked'}
                label={item.eligibility === 'eligible' ? '운영자 검토 가능' : '권고 보류'}
              />
              <span>
                {item.execution === 'not_performed'
                  ? '조치 미수행'
                  : '실제 수행 여부는 별도 조치 기록에서 확인'}
              </span>
            </div>
          )}
          <p>{str(item.text, str(item.summary, str(item.action, '세부 내용은 아래 기록 참조')))}</p>
          {item.target != null && <p>대상: {metricTarget(item)}</p>}
          {item.reason != null && <p>사유: {reportReason(str(item.reason))}</p>}
          {item.preconditions != null && (
            <details open>
              <summary>전제·확인 사항</summary>
              {Array.isArray(item.preconditions) &&
              item.preconditions.every((p) => typeof p === 'string') ? (
                <p>{strings(item.preconditions).map(reportReason).join(' ')}</p>
              ) : (
                <DataView value={item.preconditions} />
              )}
            </details>
          )}
          {strings(item.value_refs).map((ref) => {
            const metric = metrics.find((m) => m.id === ref);
            return (
              <p className="report-value-ref" key={ref}>
                {metric
                  ? `${metricName(ref)}: ${metricValue(metric)} ${metricUnit(metric)} · ${metricTarget(metric)}`
                  : `수치 참조 미확인: ${ref}`}
              </p>
            );
          })}
          {!!strings(item.evidence_refs).length && (
            <details>
              <summary>관련 근거 {strings(item.evidence_refs).length}건 보기</summary>
              <div className="head-actions">
                {strings(item.evidence_refs).map((id, i) => (
                  <button key={id} className="text-link" onClick={() => onEvidence(id)}>
                    근거 {i + 1}
                  </button>
                ))}
              </div>
            </details>
          )}
          <details>
            <summary>상세 기록</summary>
            <DataView value={item} />
          </details>
        </article>
      ))}
    </div>
  );
}
