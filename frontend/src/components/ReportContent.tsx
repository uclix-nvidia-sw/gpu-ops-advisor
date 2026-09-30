import { obj, rows, str, strings } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import {
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

const collectionLabels: Record<string, string> = {
  ok: '수집 완료',
  empty: '해당 기간 데이터 없음',
};

export function ReportContent({
  value,
  onEvidence,
}: {
  value: unknown;
  onEvidence: (id: string) => void;
}) {
  const result = obj(value),
    topics = rows(result.topics),
    observations = reportObservations(result);
  if (!Object.keys(result).length)
    return <p>아직 발행된 보고서가 없습니다. 작업 상태를 확인하세요.</p>;
  const metrics = reportMetrics(result);
  const known = metrics.filter((metric) => metric.value != null).length;
  return (
    <div className="stack">
      <section className="result-section">
        <h3>분석 요약</h3>
        <p className="report-version">
          계산 기준: {str(obj(result.versions).criteria, '미확인')} · 데이터 기준 시각:{' '}
          {formatDate(str(result.data_cutoff_at))}
        </p>
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
        <Notice>
          {known
            ? `${metrics.length}개 항목 중 ${known}개를 산출했습니다. 산출하지 못한 항목과 이유는 주제별로 표시합니다.`
            : '작업은 완료됐지만 계산 가능한 근거가 부족합니다. 수집 상태와 항목별 사유를 확인하세요.'}
        </Notice>
        {result.narrative_status === 'omitted' && (
          <p className="muted">
            AI 설명은 생성되지 않았습니다. 아래에는 원본 관측에 근거한 계산 결과만 표시합니다.
          </p>
        )}
        {str(result.summary) && <p>{str(result.summary)}</p>}
        {result.narrative_status === 'failed' && (
          <p className="muted">
            AI 설명을 생성하지 못했습니다. 계산된 수치와 근거는 아래에서 확인할 수 있습니다.
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
                      ? `${metricName(ref)}: ${metricValue(metric)} ${str(metric.unit)} (${metricTarget(metric)})`
                      : '';
                  })
                  .filter(Boolean)
                  .join(' · ') || str(fact.text)}
              </li>
            ))}
          </ul>
        )}
      </section>
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
              요청 집계 축: {strings(obj(topic.quality).requested_group_by).join(', ') || '미확인'}{' '}
              / 적용 집계 축: {strings(obj(topic.quality).applied_group_by).join(', ') || '미확인'}{' '}
              · criteria가 다른 보고서의 수치를 동일 기준으로 비교하지 않습니다.
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
                    <td>{str(metric.unit)}</td>
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
                    <td>{str(observation.metric, str(observation.query_id))}</td>
                    <td>
                      {strings(observation.statuses)
                        .map((status) => collectionLabels[status] || labels[status] || status)
                        .join(', ')}
                    </td>
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
                status={item.eligibility === 'withheld' ? 'blocked' : 'unknown'}
                label={
                  item.eligibility === 'withheld'
                    ? '권고 보류'
                    : str(item.eligibility, '자격 미확인')
                }
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
              <DataView value={item.preconditions} />
            </details>
          )}
          {strings(item.value_refs).map((ref) => {
            const metric = metrics.find((m) => m.id === ref);
            return (
              <p className="report-value-ref" key={ref}>
                {metric
                  ? `${metricName(ref)}: ${metricValue(metric)} ${str(metric.unit)} · ${metricTarget(metric)}`
                  : `수치 참조 미확인: ${ref}`}
              </p>
            );
          })}
          <div className="head-actions">
            {strings(item.evidence_refs).map((id) => (
              <button key={id} className="text-link" onClick={() => onEvidence(id)}>
                근거 {id}
              </button>
            ))}
          </div>
          <details>
            <summary>상세 기록</summary>
            <DataView value={item} />
          </details>
        </article>
      ))}
    </div>
  );
}
