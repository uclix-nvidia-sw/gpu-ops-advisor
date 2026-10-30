import {
  RcaEvaluationTrace,
  RcaStageDetails,
  RcaModelFailure,
  RcaValidationDetails,
} from './RcaEvaluationTrace';
import { RcaObservations } from './RcaObservations';
import { RcaNarrative } from './RcaNarrative';
import { gapMeaning } from '../lib/rcaGuidance';
import { rcaReasons, missingGroups, purposeLabel, modelExecution } from '../lib/rcaLabels';
import { queryName } from '../lib/report';
import { useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { apiRequest } from '../lib/api';
import { errorText, obj, rows, str, strings, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { Badge, Notice } from './ui';
import { AlarmIdentity, DataView } from './live';

const reasons = rcaReasons;
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
        사건 <Badge status={str(incident.state, str(incident.status)) || null} />
      </span>
      <span>
        검토 <Badge status={str(incident.review_status) || null} />
      </span>
    </div>
  );
}

export function IncidentDebug({ incident }: { incident: Row }) {
  const location = useLocation();
  const from = location.pathname + location.search;
  const analyses = rows(incident.analyses);
  return (
    <div className="stack">
      <AlarmIdentity record={incident} />
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
                  <th>RCA 조사</th>
                  <th>실행 상태</th>
                  <th>확인</th>
                </tr>
              </thead>
              <tbody>
                {analyses.map((a) => (
                  <tr key={str(a.job_id)}>
                    <td>
                      <Link
                        className="button primary"
                        to={`/analyses/${str(a.job_id)}`}
                        state={{ from }}
                      >
                        RCA 조사 결과 보기
                      </Link>
                    </td>
                    <td>
                      <Badge status={str(a.status) || null} />
                    </td>
                    <td>
                      <Link className="text-link" to={`/jobs/${str(a.job_id)}`} state={{ from }}>
                        실행·디버깅 기록
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
        <p className="muted">
          항목 이름에 마우스를 올리거나 클릭·Enter로 설명을 확인하세요. 미확인은 값이 없다는 뜻이며
          정상이나 0을 의미하지 않습니다.
        </p>
        <DataView value={incident} explain />
      </details>
    </div>
  );
}

export function RcaJobSummary({ job, reader = false }: { job: Row; reader?: boolean }) {
  const published = job.result_ref != null,
    result = obj(job.result);
  const attempt = rows(job.attempts).find((row) => row.attempt_no === job.attempt_no);
  const identity = (
    <>
      <AlarmIdentity record={job} rcaView />
      {str(job.incident_id) && (
        <Link className="text-link" to={`/incidents/${str(job.incident_id)}`}>
          알림 원본 보기
        </Link>
      )}
    </>
  );
  if (reader && published) return <div className="stack">{identity}</div>;
  return (
    <div className="stack">
      {identity}
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
            ? '결과 공개와 근거 충분성은 별개입니다. 아래 관측 근거와 판단 제한에서 이번 실행의 미확정 사유를 확인하세요.'
            : '내부 수집·판단 근거는 워크플로우 종료 후 일괄 저장됩니다. 근거가 보이지 않는 것만으로 수집 실패를 판단할 수 없습니다.'}
        </p>
        {(result.termination_reason || job.termination_reason || job.queue_reason) != null &&
          (result.termination_reason === 'missing_data' && strings(result.missing_inputs).length ? (
            <ul>
              {strings(result.missing_inputs).map((code) => (
                <li key={code}>
                  {gapMeaning(code, result) || reasons[code] || `추가 확인이 필요한 조건: ${code}`}
                </li>
              ))}
            </ul>
          ) : (
            <RcaReason
              value={result.termination_reason || job.termination_reason || job.queue_reason}
            />
          ))}
      </Notice>
      {attempt?.remote_call_state === 'unknown' && (
        <Notice>
          모델 통신 중단 · 원격 실행 상태 미확인. 연결 문제·응답 대기 시간 초과·취소 등을 구분하려면
          해당 시도의 실행 로그가 필요합니다. 응답 검증 실패를 뜻하지 않으며, 모델 서버에서 실행이
          끝났는지도 확인되지 않았습니다.
        </Notice>
      )}
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
                  <strong>
                    {str(v.query_id, '조회 ID 미확인')} · {queryName(str(v.query_id))}
                  </strong>
                  <small className="cell-sub">
                    {str(v.cluster_id, '클러스터 미확인')} ·{' '}
                    {str(v.query_version, 'revision 미확인')}
                  </small>
                  <small className="cell-sub">
                    {v.time_start ? formatDate(str(v.time_start)) : '시작 미확인'} →{' '}
                    {v.time_end ? formatDate(str(v.time_end)) : '종료 미확인'}
                  </small>
                </td>
                <td>
                  <Badge
                    status={str(v.tool_status) || null}
                    label={collectionNames[str(v.tool_status)]}
                  />
                </td>
                <td>
                  <span title={str(q.datasource_uid)}>
                    {obj(v.input).logql
                      ? 'Loki'
                      : obj(v.input).expr
                        ? 'Mimir'
                        : q.original_samples === true
                          ? 'Mimir'
                          : q.original_samples === false
                            ? 'Loki'
                            : '유형 미확인'}{' '}
                    ({str(v.cluster_id, '클러스터 미확인')})
                  </span>
                  <small className="cell-sub">
                    완전성:{' '}
                    {v.tool_status === 'empty' && q.complete === true
                      ? '조회 정상 완료 · 데이터 0건'
                      : q.complete === true
                        ? '조회 완료'
                        : q.complete === false
                          ? '불완전'
                          : '미확인'}
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

export function EvidenceEvaluation({ record }: { record: Row }) {
  const next = strings(record.next_queries);
  const selection = obj(record.followup_selection);
  const selectionText: Record<string, string> = {
    selected: '필요한 보조 조회를 선택했습니다.',
    explicit_stop:
      '모델이 추가 조회 없이 종료하도록 선택했습니다. 근거가 충분해졌다는 뜻은 아닙니다.',
    invalid_response: '추가 조회 선택 응답이 형식 검증을 통과하지 못했습니다.',
    model_unavailable: '모델 요청이 완료되지 않아 추가 조회를 선택하지 못했습니다.',
    policy_selected: 'Runbook 정책에 따라 보조 조회를 배정했습니다.',
    selection_conditions_missing:
      '조회 선택 조건 미설정: Runbook에 보조 조회 조건을 설정해야 합니다. 선택용 LLM은 호출하지 않았습니다.',
    conditions_not_met:
      '보조 조회의 Runbook 조건이 충족되지 않았습니다. 근거가 충분하다는 뜻은 아닙니다.',
    registered_default: '승인된 조회 후보를 코드 정책에 따라 배정했습니다.',
  };
  return (
    <article className="data-item">
      <h4>근거 평가 · {Number(record.round ?? 0) + 1}회차</h4>
      <p>
        판단: <RcaReason value={record.decision} />
      </p>
      <ul>
        {strings(record.evidence_gap).map((gap) => (
          <li key={gap}>{gapMeaning(gap, {}) || reasons[gap] || gap}</li>
        ))}
      </ul>
      <p>
        {next.length
          ? `다음 조회: ${next.map(queryName).join(' · ')}`
          : '이번 회차 이후 추가 조회를 배정하지 않았습니다.'}
      </p>
      {selectionText[str(selection.status)] && (
        <p>
          {selectionText[str(selection.status)]}
          {selection.attempts === 2 ? ' 선택 응답의 형식 복구를 한 차례 시도했습니다.' : ''}
        </p>
      )}
      {rows(selection.validation_details).length > 0 && (
        <RcaValidationDetails diagnostic={selection} />
      )}
      {record.stop_reason != null && (
        <p>
          수집 종료 이유: <RcaReason value={record.stop_reason} />
        </p>
      )}
      <details>
        <summary>확인한 사실·확장 정책·남은 예산</summary>
        <DataView value={record} />
      </details>
    </article>
  );
}

export function RcaEvidence({
  result,
  job,
  onEvidence,
}: {
  result: Row;
  job: Row;
  onEvidence: (id: string) => void;
}) {
  const refs = [...new Set(strings(result.evidence_refs))],
    [count, setCount] = useState(8);
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
      <RcaEvaluationTrace items={items} onEvidence={onEvidence} />
      {!!trace.length && (
        <details>
          <summary>개발용 조사 단계 원본 · {trace.length}건</summary>
          <div className="stack">
            {trace.map((v) => (
              <article className="data-item" key={str(v.id)}>
                <h4>{str(v.query_id)}</h4>
                <RcaStageDetails record={v} onEvidence={onEvidence} />
                <DataView value={v.snapshot} field="snapshot" />
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

export function RcaResult({
  job,
  onEvidence,
  showEvidence = true,
  evaluationExpanded = false,
  reader = false,
  alarm,
}: {
  job: Row;
  onEvidence: (id: string) => void;
  showEvidence?: boolean;
  evaluationExpanded?: boolean;
  /** Operator view: the report only; evidence and processing records stay in developer mode. */
  reader?: boolean;
  /** The incident now, for the report's live alert state. */
  alarm?: Row;
}) {
  const result = obj(job.result),
    analysis = obj(obj(result.quality).analysis),
    synthesis = obj(analysis.synthesis),
    usage = obj(result.llm_usage);
  const evidenceLabels = Object.fromEntries(
    rows(obj(result.quality).evidence_catalog).map((e) => [
      str(e.id),
      `${str(e.label)} · ${formatDate(str(obj(e.time_range).start))}–${formatDate(str(obj(e.time_range).end))}${typeof e.sample_count === 'number' ? ` · ${e.sample_count}건` : ''}`,
    ]),
  );
  if (reader)
    return (
      <div className="stack">
        <RcaJobSummary job={job} reader />
        {job.result_ref != null && (
          <RcaNarrative result={result} consolidateChecks onEvidence={onEvidence} alarm={alarm} />
        )}
      </div>
    );
  return (
    <div className="stack">
      <RcaJobSummary job={job} />
      {job.result_ref != null && (
        <>
          <RcaNarrative
            result={result}
            consolidateChecks
            evaluationExpanded={evaluationExpanded}
            onEvidence={onEvidence}
            alarm={alarm}
          />
          {obj(obj(result.quality).triage_observations).schema !== 'rca-triage-observations/1' &&
            obj(obj(result.quality).analysis).workflow !== 'single_collection' && (
              <RcaObservations result={result} onEvidence={onEvidence} />
            )}
          {showEvidence && (
            <RcaEvidence
              key={str(job.result_ref)}
              result={result}
              job={job}
              onEvidence={onEvidence}
            />
          )}
          <details className="result-section">
            <summary>분석 요약·LLM 실행 기록</summary>
            <h3>분석 요약</h3>
            <dl className="details">
              <dt>수집 종료 사유</dt>
              <dd>
                {(
                  {
                    fast_path: '결정적 판단 경로',
                    sufficient: '필수 조건 충족',
                    no_remaining_queries: '허용된 추가 조회 없음',
                    query_budget_exhausted: '조회 예산 소진',
                    deadline_exhausted: '작업 기한 도달',
                    round_limit_reached: '수집 회차 상한 도달',
                    selection_conditions_missing: '조회 선택 조건 미설정',
                    followup_not_selected: '추가 조회를 선택하지 못함',
                  } as Record<string, string>
                )[str(analysis.collection_stop_reason)] ||
                  '기록 없음 · 이전 결과의 종료 이유는 추정하지 않습니다.'}
              </dd>
              {Array.isArray(analysis.remaining_queries) && (
                <>
                  <dt>실행하지 않은 조회 후보</dt>
                  <dd>{strings(analysis.remaining_queries).join(', ') || '없음'}</dd>
                </>
              )}
              {obj(analysis.fleet_report_diagnostics).reports != null && (
                <>
                  <dt>Fleet 상태 보고 해석</dt>
                  <dd>
                    <p>
                      읽은 Fleet 상태 보고: {String(obj(analysis.fleet_report_diagnostics).reports)}
                      건. 생산자 시각 누락·초기값:{' '}
                      {String(
                        obj(analysis.fleet_report_diagnostics).missing_or_zero_producer_time ??
                          '미기록',
                      )}
                      건. 현재 상태로 검증되지 않은 보고:{' '}
                      {String(
                        obj(analysis.fleet_report_diagnostics).unverified_state_reports ?? '미기록',
                      )}
                      건.
                    </p>
                  </dd>
                  <dd>
                    로그 수집 성공은 상태 검증 성공이 아닙니다. 발생 시각이 비어 있거나 초기값이면
                    Loki 기록 시각을 실제 장애 발생 시각으로 대신 사용하지 않습니다. 장비 목록은
                    노드 재고이며 오류 장치 확정 정보가 아닙니다.
                  </dd>
                </>
              )}
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
              <dt>RCA 분석 요청 시도</dt>
              <dd>
                {typeof synthesis.request_attempts === 'number'
                  ? `${synthesis.request_attempts}건`
                  : '미확인 · 구 결과에는 단계별 기록이 없습니다.'}
              </dd>
              <dt>RCA 분석 응답 기록</dt>
              <dd>
                {typeof synthesis.response_calls === 'number'
                  ? `${synthesis.response_calls}건`
                  : '미확인'}
              </dd>
              {synthesis.error_code != null && (
                <>
                  <dt>RCA 분석 실패·제한 사유</dt>
                  <dd>
                    <RcaModelFailure diagnostic={synthesis} />
                  </dd>
                </>
              )}
              <dt>분석 상태</dt>
              <dd>
                {analysis.status === 'failed' ? (
                  <span>
                    LLM 분석 미완료 <code>failed</code> · {modelExecution(synthesis)}
                  </span>
                ) : (
                  <RcaReason value={analysis.status} />
                )}
              </dd>
            </dl>
            <p className="muted">
              전체 LLM 응답 기록에는 후속 조회 선택과 최종 보고서 편집도 포함됩니다. RCA 분석 성공
              횟수가 아닙니다. LLM 기록 0건만으로 연결 실패를 판단하지 않습니다. 요청 실패·생략
              여부는 분석 상태와 근거를 함께 확인하세요.
            </p>
            <p>{str(result.summary)}</p>
          </details>
          <details className="result-section">
            <summary>판단 제한·검증 진단 상세</summary>
            <RcaQualityGuidance result={result} />
          </details>
          {(
            [
              ['관측 사실', result.facts],
              ['원인 후보', result.cause_candidates],
              ['권장 조치·적용 조건', result.recommendations],
              ['조사별 판단', result.assessments],
            ] as const
          ).map(([title, value]) => (
            <details className="result-section" key={title}>
              <summary>{title} · 구조화된 분석 기록</summary>
              {title === '조사별 판단' ? (
                rows(value).map((assessment, index) => (
                  <article
                    key={str(assessment.assessment_id) || str(assessment.purpose_id) || index}
                  >
                    <h4>{str(assessment.question) || purposeLabel(str(assessment.purpose_id))}</h4>
                    <DataView value={assessment} evidenceLabels={evidenceLabels} />
                  </article>
                ))
              ) : (
                <DataView value={value} evidenceLabels={evidenceLabels} />
              )}
            </details>
          ))}
          {!!rows(result.runbook_revisions).length && (
            <details className="result-section">
              <summary>참조 Runbook · 선택 기록</summary>
              {rows(result.runbook_revisions).some((book) => book.origin === 'published') && (
                <p>
                  발행 Runbook 선택 기록이 있습니다. 선택은 필수 근거 충족이나 원인 확정을 의미하지
                  않습니다. 조사별 판단의 부족 항목을 확인하세요.
                  {rows(result.runbook_revisions).some((book) => book.origin === 'builtin') &&
                    ' 기본 일반 조사 템플릿도 추가 사용했습니다. 발행 Runbook이 없었다는 의미가 아닙니다.'}
                </p>
              )}
              <DataView field="runbook_revisions" value={result.runbook_revisions} />
            </details>
          )}
          <details>
            <summary>공개 결과 원본 · 모델/Runbook revision 포함</summary>
            <DataView value={result} />
          </details>
        </>
      )}
      <details>
        <summary>작업 연결 정보</summary>
        <p className="muted">
          접수 {formatDate(str(job.created_at))} · 작업 ID {str(job.id)}
        </p>
      </details>
    </div>
  );
}

export function RcaQualityGuidance({ result }: { result: Row }) {
  const groups = missingGroups(strings(result.missing_inputs));
  const analysis = obj(obj(result.quality).analysis),
    synthesis = obj(analysis.synthesis),
    gate = obj(synthesis.repair_gate);
  const repairNames: Record<string, string> = {
    repaired: '수정 응답 검증 통과',
    failed: '수정 응답을 채택하지 못함',
    budget_exhausted: '남은 모델 예산 부족으로 수정 요청 생략',
    deadline_exhausted: '실행 기한 만료로 수정 요청 생략',
    budget_and_deadline_exhausted: '예산 부족·실행 기한 만료로 수정 요청 생략',
    budget_or_deadline_exhausted: '예산 또는 기한으로 생략 · 구 기록은 구체적 원인을 구분하지 않음',
  };
  return (
    <section className="result-section stack" aria-label="판단 제한과 다음 확인">
      <h3>확정하지 못한 이유</h3>
      {!rows(result.narrative).some((s) => s.id === 'guidance' && str(s.text)) &&
        rows(result.narrative).some((s) => s.id === 'next' && str(s.text)) && (
          <ul>
            {[
              ...new Set(
                rows(result.narrative)
                  .filter((s) => s.id === 'next')
                  .flatMap((s) => str(s.text).split(/\n\s*\n/))
                  .filter(Boolean),
              ),
            ].map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        )}
      {result.termination_reason === 'missing_data' && (
        <p>
          현재 결과만으로 확정할 수 없는 내용과 다음 확인 절차입니다. 조회 실패와 현재 상태·원인
          미확정은 서로 다른 문제입니다.
        </p>
      )}
      {groups.length ? (
        <>
          <p>{groups.length}개 범주의 미충족 조건입니다. 저장된 결과 품질은 변경하지 않습니다.</p>
          {groups.map((group) => (
            <article className="data-item" key={group.id}>
              <h4>
                {group.name} · {group.items.length}개
              </h4>
              <ul>
                {group.items.map((code) => (
                  <li key={code}>
                    {gapMeaning(code, result) ||
                      reasons[code] ||
                      '분류되지 않은 조건입니다. 원본 사유를 확인하세요.'}
                    <details>
                      <summary>진단 코드</summary>
                      <code>{code}</code>
                    </details>
                  </li>
                ))}
              </ul>
              <p>
                <strong>다음 확인: </strong>
                {group.next}
              </p>
            </article>
          ))}
        </>
      ) : (
        <p>
          {Array.isArray(result.missing_inputs)
            ? '보고된 부족 항목이 없습니다. 원인이 확정됐다는 의미는 아닙니다.'
            : '이 결과에는 미충족 조건 목록이 없습니다. 구 결과의 분석 한계와 원본을 확인하세요.'}
        </p>
      )}
      <p className="muted">
        이 서비스는 조치를 권고하며 장비 조치를 실행하지 않습니다. 미수행 자체는 분석 실패가
        아닙니다. 권고의 적용 조건은 별도로 검토하세요.
      </p>
      {(rows(result.narrative).some((s) => s.id === 'limits') ||
        strings(result.limitations).length > 0) && (
        <details>
          <summary>분석 한계 원문</summary>
          <p>위 안내와 겹치는 저장 설명은 여기에서 확인할 수 있습니다.</p>
          {[
            ...new Set(
              [
                ...rows(result.narrative)
                  .filter((s) => s.id === 'limits')
                  .flatMap((s) => str(s.text).split(/\n\s*\n/)),
                ...strings(result.limitations),
              ].filter(Boolean),
            ),
          ].map((text, i) => (
            <p key={i}>{text}</p>
          ))}
        </details>
      )}
      {(synthesis.repair_status != null || synthesis.error_code != null) && (
        <details>
          <summary>LLM 분석·수정 요청 진단</summary>
          <p>
            분석 상태:{' '}
            {analysis.status === 'failed' ? (
              <span>
                LLM 분석 미완료 <code>failed</code> · {modelExecution(synthesis)}
              </span>
            ) : synthesis.completion_mode === 'validated_subset' ||
              (analysis.status === 'complete' && synthesis.repair_status === 'failed') ? (
              <span>응답 일부만 사용했습니다. 수정 검증이 완전히 통과한 결과는 아닙니다.</span>
            ) : (
              <RcaReason value={analysis.status} />
            )}
          </p>
          {synthesis.error_code != null && (
            <p>
              기록된 거절 사유: <RcaReason value={synthesis.error_code} />
            </p>
          )}
          <p>
            수정 요청 결과: {repairNames[str(synthesis.repair_status)] || '상세 기록 미확인'}{' '}
            <code>{str(synthesis.repair_status)}</code>
          </p>
          {rows(synthesis.validation_failures).map((attempt, i) => (
            <div key={i}>
              <h4>분석 응답 {String(attempt.attempt ?? i + 1)}회차 검사</h4>
              {rows(attempt.violations).map((violation, j) => (
                <p key={j}>
                  {violation.rule === 'identity_is_not_cause'
                    ? '장치 식별의 불확실성을 장애 원인으로 제시한 문장을 거절했습니다. 판단 제한으로 설명해야 합니다.'
                    : violation.rule === 'non_korean'
                      ? `${typeof violation.hypothesis_index === 'number' ? '원인 후보' : '분석 한계'} 문장이 한국어 설명 기준을 충족하지 못했습니다.`
                      : violation.rule === 'numeric'
                        ? `등록된 근거로 검증되지 않은 숫자 표현이 ${typeof violation.hypothesis_index === 'number' ? '원인 후보' : '분석 한계'} 문장에 포함됐습니다.`
                        : str(violation.code, '응답 검증 실패')}
                  {typeof violation.limitation_index === 'number' &&
                    ` (한계 문장 ${violation.limitation_index + 1})`}
                  {typeof violation.hypothesis_index === 'number' &&
                    ` (원인 후보 ${violation.hypothesis_index + 1})`}
                </p>
              ))}
            </div>
          ))}
          {rows(synthesis.validation_failures).length > 0 && (
            <p>
              거절 문장 원문은 저장되지 않아 정확한 문구는 복원할 수 없습니다. 이 진단은 최종 보고서
              편집 성공 여부와 별개입니다.
            </p>
          )}
          <dl className="details">
            {Object.entries({
              remaining_budget: '남은 모델 예산',
              prompt_bound: '입력 예산 추정 상한',
              available_output_cap: '수정 응답 출력 상한',
              remaining_seconds: '기한까지 남은 초',
            }).map(([key, label]) =>
              typeof gate[key] === 'number' && Number.isFinite(gate[key]) ? (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{String(gate[key])}</dd>
                </div>
              ) : null,
            )}
          </dl>
          <p>
            거절 기록과 조회 성공 여부는 별개입니다. 수정이 통과해도 장치 상태나 원인을 자동
            확정하지 않습니다.
          </p>
        </details>
      )}
    </section>
  );
}
