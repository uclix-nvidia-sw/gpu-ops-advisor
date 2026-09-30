import { useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiRequest } from '../lib/api';
import { errorText, obj, rows, str, strings, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { Badge, Notice } from './ui';
import { DataView } from './live';

const reasons: Record<string, string> = {
  sufficient: '필수 근거를 충족했습니다.',
  degraded: '수집 실패 또는 불완전한 관측이 있습니다.',
  conflicted: '관측 상태가 상충합니다.',
  insufficient_actionable: '근거가 부족하며 추가 조회 후보가 있습니다.',
  insufficient_blocked: '근거가 부족하고 추가 조회 후보가 없습니다.',
  complete: '분석 응답 검증을 완료했습니다. 원인 확정 여부는 후보별 근거를 확인하세요.',
  query_failed: '관측 조회가 실패했습니다. 수집 현황에서 오류 코드를 확인하세요.',
  loki_entry_limit_exceeded: 'Loki 조회 행 제한을 초과했습니다.',
  mcp_tool_error: 'MCP 도구가 오류를 반환했습니다. Worker·MCP 로그를 확인하세요.',
  invalid_mcp_response: 'MCP 응답을 해석하지 못했습니다.',
  sample_limit_exceeded: '조회 행 수가 제한에 도달해 일부 데이터가 누락될 수 있습니다.',
  response_byte_limit: '응답 크기 제한으로 관측을 보존하지 못했습니다.',
  budget_exhausted: '조회 횟수 또는 시간 예산이 소진됐습니다.',
  no_usable_evidence: '분석에 사용할 유효한 관측 근거가 없습니다.',
  synthesis_no_usable_evidence: '유효한 관측 근거가 없어 LLM 분석을 생략했습니다.',
  unconfigured: '이 작업에 사용할 LLM 연결이 구성되지 않았습니다.',
  synthesis_unconfigured: 'LLM 연결이 구성되지 않아 분석을 생략했습니다.',
  skipped_runbook: 'Runbook의 결정적 판단 경로를 사용했습니다.',
  missing_data: '필수 근거가 부족합니다. 부족 항목을 확인하세요.',
  conflicting_evidence: '관측 근거가 서로 상충합니다.',
  evidence_sufficient: '코드의 근거 충분성 기준을 충족했습니다.',
  causal_confirmation_evidence: '원인을 뒷받침할 추가 근거가 필요합니다.',
  producer_contract: '로그 생산자의 상태 해석 계약이 확인되지 않았습니다.',
  incident_mapping: '관측과 사건 대상의 연결이 확인되지 않았습니다.',
  stale_alert: '허용 기간을 벗어난 오래된 알람입니다.',
  future_timestamp: '미래 시각으로 기록된 알람입니다.',
  analysis_policy_unconfigured: '적용할 분석 정책이 없습니다.',
  alarm_resolved: '알람이 해제되어 새 RCA 접수 대상이 아닙니다.',
  incident_closed: '종결된 사건입니다.',
  repeated_evidence: '기존과 같은 증거로 새 RCA를 생성하지 않았습니다.',
};
export function RcaReason({ value }: { value: unknown }) {
  const code = str(value);
  return code ? (
    <span>
      {reasons[code] || labels[code] || '사유 코드'} <code>{code}</code>
    </span>
  ) : (
    <span>사유 미확인</span>
  );
}

export function IncidentStates({ incident }: { incident: Row }) {
  return (
    <div className="rca-states">
      <span>
        알람{' '}
        <Badge
          status={str(incident.alarm_status) || null}
          label={
            incident.alarm_status === 'resolved'
              ? '해제됨'
              : incident.alarm_status === 'firing'
                ? '발생 중'
                : undefined
          }
        />
      </span>
      <span>
        사건 <Badge status={str(incident.state, str(incident.status)) || null} />
      </span>
      <span>
        검토 <Badge status={str(incident.review_status) || null} />
      </span>
    </div>
  );
}

export function IncidentDebug({ incident }: { incident: Row }) {
  const analyses = rows(incident.analyses);
  return (
    <div className="stack">
      <IncidentStates incident={incident} />
      <DataView
        value={{
          target: incident.target,
          scope: incident.scope,
          occurred_at: incident.occurred_at,
          evidence_version: incident.evidence_version,
        }}
      />
      {incident.rca_eligibility_reason != null && (
        <Notice>
          <RcaReason value={incident.rca_eligibility_reason} />
        </Notice>
      )}
      <section className="result-section">
        <h3>연결된 RCA 작업 · {analyses.length}건</h3>
        <p className="muted">알람 해제는 원인 확인이나 장비 복구 완료를 의미하지 않습니다.</p>
        {analyses.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>작업 ID</th>
                  <th>실행 상태</th>
                  <th>확인</th>
                </tr>
              </thead>
              <tbody>
                {analyses.map((a) => (
                  <tr key={str(a.job_id)}>
                    <td>
                      <Link className="text-link" to={`/jobs/${str(a.job_id)}`}>
                        {str(a.job_id)}
                      </Link>
                    </td>
                    <td>
                      <Badge status={str(a.status) || null} />
                    </td>
                    <td>
                      <Link className="text-link" to={`/analyses/${str(a.job_id)}`}>
                        결과·수집 근거
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Notice>
            연결된 RCA 작업이 없습니다. 분석 대상 여부와 Incident의 전달 기록을 확인하세요. 현재
            화면에는 webhook 접수·outbox 이력이 제공되지 않습니다.
          </Notice>
        )}
      </section>
      <details>
        <summary>사건 원본 필드</summary>
        <DataView value={incident} />
      </details>
    </div>
  );
}

export function RcaJobSummary({ job }: { job: Row }) {
  const published = job.result_ref != null,
    result = obj(job.result);
  return (
    <div className="stack">
      {str(job.incident_id) && (
        <Link className="text-link" to={`/incidents/${str(job.incident_id)}`}>
          원본 사건 · {str(job.incident_id)}
        </Link>
      )}
      <Notice>
        <strong>
          {published
            ? '결과 공개 완료'
            : job.status === 'failed'
              ? '실행 실패 · 공개 결과 없음'
              : '아직 공개된 결과가 없습니다.'}
        </strong>
        <p>
          {published
            ? '결과 공개와 근거 충분성은 별개입니다. 결과 품질과 분석 사유를 함께 확인하세요.'
            : '내부 수집·판단 근거는 워크플로우 종료 후 일괄 저장됩니다. 근거가 보이지 않는 것만으로 수집 실패를 판단할 수 없습니다.'}
        </p>
        {(result.termination_reason || job.termination_reason || job.queue_reason) != null && (
          <RcaReason
            value={result.termination_reason || job.termination_reason || job.queue_reason}
          />
        )}
      </Notice>
      <p className="muted">
        서버 단계: <code>{str(job.stage, '미확인')}</code> · 시도{' '}
        {typeof job.attempt_no === 'number' ? job.attempt_no : '미확인'}. 개별 조회의 실시간
        진행률은 제공되지 않습니다.
      </p>
    </div>
  );
}

const collectionNames: Record<string, string> = {
  ok: '수집 완료',
  partial: '부분 수집',
  unavailable: '수집 실패·불가',
  empty: '빈 결과',
};
export function EvidenceRows({
  items,
  onEvidence,
}: {
  items: Row[];
  onEvidence: (id: string) => void;
}) {
  const ordered = [...items].sort((a, b) => {
    const rank = (v: Row) =>
      ({ unavailable: 0, partial: 1, empty: 2, ok: 3 })[str(v.tool_status)] ?? 4;
    return (
      rank(a) - rank(b) ||
      str(a.query_id).localeCompare(str(b.query_id)) ||
      str(a.time_start).localeCompare(str(b.time_start))
    );
  });
  return (
    <div className="table-wrap">
      <table className="rca-evidence">
        <thead>
          <tr>
            <th>조회·구간</th>
            <th>상태</th>
            <th>데이터소스·품질</th>
            <th>사유·상세</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((v) => {
            const q = obj(v.quality);
            return (
              <tr key={str(v.id)}>
                <td>
                  <strong>{str(v.query_id, '조회 ID 미확인')}</strong>
                  <small className="cell-sub">
                    {str(v.cluster_id, '클러스터 미확인')} ·{' '}
                    {str(v.query_version, 'revision 미확인')}
                  </small>
                  <small className="cell-sub">
                    {str(v.time_start, '시작 미확인')} → {str(v.time_end, '종료 미확인')}
                  </small>
                </td>
                <td>
                  <Badge
                    status={str(v.tool_status) || null}
                    label={collectionNames[str(v.tool_status)]}
                  />
                </td>
                <td>
                  {str(q.datasource_uid, '데이터소스 미확인')}
                  <small className="cell-sub">
                    완전성:{' '}
                    {q.complete === true ? '완전' : q.complete === false ? '불완전' : '미확인'}
                  </small>
                  <small className="cell-sub">
                    응답 표본: {typeof q.sample_count === 'number' ? q.sample_count : '미확인'}
                  </small>
                </td>
                <td>
                  {q.reason != null && (
                    <p>
                      <RcaReason value={q.reason} />
                    </p>
                  )}
                  {q.error_code != null && (
                    <p>
                      <RcaReason value={q.error_code} />
                    </p>
                  )}
                  <button className="text-link" onClick={() => onEvidence(str(v.id))}>
                    근거 상세
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RcaEvidence({
  result,
  job,
  onEvidence,
}: {
  result: Row;
  job: Row;
  onEvidence: (id: string) => void;
}) {
  const refs = [...new Set(strings(result.evidence_refs))],
    [count, setCount] = useState(0);
  const queries = useQueries({
    queries: refs.slice(0, count).map((id) => ({
      queryKey: ['api', `/evidence/${encodeURIComponent(id)}`, job.id, job.attempt_no],
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const evidence = await apiRequest<Row>(`/evidence/${encodeURIComponent(id)}`, { signal });
        if (
          evidence.id !== id ||
          evidence.job_id !== job.id ||
          (typeof job.attempt_no === 'number' && evidence.attempt_no !== job.attempt_no)
        )
          throw new Error('다른 작업·시도의 근거입니다. 결과를 다시 조회하세요.');
        return evidence;
      },
      retry: false,
      staleTime: Infinity,
    })),
  });
  const items = queries.flatMap((q) => (q.data ? [q.data] : [])),
    collecting = queries.some((q) => q.isFetching);
  const observations = items.filter((v) => /^D\d+$/.test(str(v.query_id))),
    trace = items.filter((v) => !/^D\d+$/.test(str(v.query_id)));
  return (
    <section className="result-section stack">
      <h3>수집·판단 근거</h3>
      <p>
        공개 결과가 참조한 근거 {refs.length}건 중 {items.length}건 조회. 요청 부하를 줄이기 위해
        8건씩 불러옵니다.
      </p>
      <p className="muted">
        D-query는 구간별로 표시하며 표본을 합산하지 않습니다. query 원문은 현재 API에서 제공하지
        않습니다. 근거 상세에서 snapshot·실제 요청 시간 범위 등 제공된 필드를 확인할 수 있습니다.
      </p>
      {count < refs.length && (
        <button
          className="button"
          disabled={collecting}
          onClick={() => setCount(Math.min(count + 8, refs.length))}
        >
          {count ? '근거 8건 더 보기' : '수집·판단 근거 불러오기'}
        </button>
      )}
      {collecting && <p role="status">근거를 불러오는 중…</p>}
      {queries.map(
        (q, i) =>
          q.isError && (
            <div role="alert" key={refs[i]}>
              <p>
                근거 {refs[i]} 조회 실패: {errorText(q.error)}
              </p>
              <button className="button" onClick={() => q.refetch()}>
                해당 근거 다시 조회
              </button>
            </div>
          ),
      )}
      {observations.length > 0 && <EvidenceRows items={observations} onEvidence={onEvidence} />}
      {count > 0 && !collecting && observations.length === 0 && (
        <p>
          현재 불러온 근거에는 D-query 기록이 없습니다. 생략된 경로인지, 아직 조회하지 않은 근거가
          있는지 확인하세요.
        </p>
      )}
      {!!trace.length && (
        <details>
          <summary>조사 단계 기록 · {trace.length}건</summary>
          <div className="stack">
            {trace.map((v) => (
              <article className="data-item" key={str(v.id)}>
                <h4>{str(v.query_id)}</h4>
                <DataView value={v.snapshot} />
                <button className="text-link" onClick={() => onEvidence(str(v.id))}>
                  근거 상세 · {str(v.id)}
                </button>
              </article>
            ))}
          </div>
        </details>
      )}
      {!refs.length && <p>공개 결과에 근거 참조가 없습니다. 수집 성공을 확인할 수 없습니다.</p>}
    </section>
  );
}

export function RcaResult({ job, onEvidence }: { job: Row; onEvidence: (id: string) => void }) {
  const result = obj(job.result),
    analysis = obj(obj(result.quality).analysis),
    usage = obj(result.llm_usage);
  return (
    <div className="stack">
      <RcaJobSummary job={job} />
      {job.result_ref != null && (
        <>
          <section className="result-section">
            <h3>분석 요약</h3>
            <dl className="details">
              <dt>결과 품질</dt>
              <dd>
                <Badge status={str(result.result_status) || null} />
              </dd>
              <dt>충분성 판단</dt>
              <dd>
                <RcaReason value={analysis.sufficiency} />
              </dd>
              <dt>분석 경로</dt>
              <dd>
                {analysis.fast_path === true
                  ? '결정적 Runbook 판단'
                  : analysis.fast_path === false
                    ? '증거 기반 분석'
                    : '미확인'}
              </dd>
              <dt>LLM 응답 사용 기록</dt>
              <dd>{typeof usage.calls === 'number' ? `${usage.calls}건` : '미확인'}</dd>
              <dt>분석 상태</dt>
              <dd>
                <RcaReason value={analysis.status} />
              </dd>
            </dl>
            <p className="muted">
              LLM 기록 0건만으로 연결 실패를 판단하지 않습니다. 요청 실패·생략 여부는 분석 상태와
              근거를 함께 확인하세요.
            </p>
            <p>{str(result.summary)}</p>
          </section>
          <section className="result-section">
            <h3>부족한 근거 · {strings(result.missing_inputs).length}개</h3>
            {strings(result.missing_inputs).length ? (
              <ul>
                {strings(result.missing_inputs).map((v) => (
                  <li key={v}>
                    <RcaReason value={v} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>보고된 부족 항목이 없습니다. 원인이 확정됐다는 의미는 아닙니다.</p>
            )}
            <DataView value={result.limitations} />
          </section>
          <RcaEvidence
            key={str(job.result_ref)}
            result={result}
            job={job}
            onEvidence={onEvidence}
          />
          {(
            [
              ['관측 사실', result.facts],
              ['원인 후보', result.cause_candidates],
              ['검토 권고 · 장비 조치 미수행', result.recommendations],
              ['목적별 판단', result.assessments],
            ] as const
          ).map(([title, value]) => (
            <section className="result-section" key={title}>
              <h3>{title}</h3>
              <DataView value={value} />
            </section>
          ))}
          <details>
            <summary>공개 결과 원본 · 모델/Runbook revision 포함</summary>
            <DataView value={result} />
          </details>
        </>
      )}
      <p className="muted">
        접수 {formatDate(str(job.created_at))} · 작업 ID {str(job.id)}
      </p>
    </div>
  );
}
