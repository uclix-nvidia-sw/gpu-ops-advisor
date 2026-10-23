import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import {
  debugTab,
  debugTabs,
  evidenceRelation,
  jobRelation,
  knowledgeRelation,
  returnPath,
  selectedAttempt,
} from '../lib/debug';
import { obj, rows, str, useResource, type Row } from '../lib/live';
import { ReportOrigin, ReportTimeNote, ReportScope } from './ReportMeta';
import { formatDate } from '../lib/domain';
import { reportTitle } from '../lib/workflow';
import { Reviews, ReportExports } from '../pages/Results';
import { AlarmIdentity, DataView, QueryState } from './live';
import { Badge, Notice } from './ui';
import { RcaResult } from './RcaDebug';
import {
  InputTrace,
  StoredEvidence,
  JobComparison,
  RawRecord,
  AttemptComparison,
} from './TraceView';
import { ReportContent } from './ReportContent';
import { ReportDeletionNotice } from './ReportDeletion';
import { RecordInspector } from './RecordInspector';
import { WorkflowGuide } from './WorkflowGuide';
import { useApp } from '../lib/store';
import { rcaReasons } from '../lib/rcaLabels';

export function JobDebug({ job, onAction }: { job: Row; onAction: (action: string) => void }) {
  const app = useApp();
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const contextParams = new URLSearchParams(params);
  const from = params.get('from') || location.state?.from || location.state?.reportList;
  if (from) contextParams.set('from', returnPath(from));
  const tab = debugTab(params.get('tab'));
  const attempts = rows(job.attempts);
  const requestedAttempt = params.get('attempt');
  const attempt = selectedAttempt(job, requestedAttempt);
  const selected = attempts.find((a) => a.attempt_no === attempt);
  const failure = str(
    selected
      ? selected.termination_reason
      : requestedAttempt === null
        ? job.termination_reason
        : undefined,
  );
  const [relationKey, setRelationKey] = useState('');
  const evidenceId = params.get('evidence') || '';
  const [knowledgeIndex, setKnowledgeIndex] = useState<number | null>(null);
  const result = job.result_ref != null ? obj(job.result) : {};
  const traceQuery = useResource(`/jobs/${encodeURIComponent(str(job.id))}/trace`);
  const trace = traceQuery.data?.job_id === job.id ? traceQuery.data : undefined;
  const versions = obj(trace?.versions ?? result.versions);
  const knowledge = rows(versions.knowledge);
  const evidenceAttempt = attempt;
  const updateEvidence = (id: string, nextAttempt = attempt) => {
    const next = new URLSearchParams(contextParams);
    if (id) next.set('evidence', id);
    else next.delete('evidence');
    if (nextAttempt !== null) next.set('attempt', String(nextAttempt));
    setParams(next, { state: location.state });
  };
  const relation =
    evidenceId && evidenceAttempt !== null
      ? evidenceRelation({ ...job, attempt_no: evidenceAttempt }, evidenceId, true)
      : knowledgeIndex !== null && knowledge[knowledgeIndex]
        ? knowledgeRelation(
            knowledge[knowledgeIndex],
            trace ? 'jobs.versions.knowledge[]' : undefined,
          )
        : relationKey
          ? jobRelation(job, relationKey, typeof attempt === 'number' ? attempt : undefined, trace)
          : null;
  const inspect = (key: string) => {
    setKnowledgeIndex(null);
    updateEvidence('');
    setRelationKey(key);
  };
  const onEvidence = (id: string) => {
    setKnowledgeIndex(null);
    setRelationKey('');
    updateEvidence(id, tab === 'result' ? selectedAttempt(job, null) : evidenceAttempt);
  };
  const keyButton = (key: string, label: string) => (
    <button className="button" onClick={() => inspect(key)} aria-expanded={relationKey === key}>
      {label} · 연결 정보
    </button>
  );
  return (
    <>
      {app.mode === 'workbench' && failure && (
        <aside className="console-failure" role="note">
          <div>
            <strong>{selected ? '선택한 시도의 종료 사유' : '작업 종료 사유'}</strong>
            <p>{rcaReasons[failure] || failure}</p>
            <code>{failure}</code>
          </div>
          <div className="head-actions">
            <Link
              className="button"
              to="/settings/backend"
              state={{ from: location.pathname + location.search }}
            >
              현재 서비스 상태
            </Link>
            <Link
              className="button"
              to="/settings/models"
              state={{ from: location.pathname + location.search }}
            >
              현재 모델 설정
            </Link>
          </div>
        </aside>
      )}
      <section className="debug-summary stack">
        {job.kind === 'rca' ? (
          <AlarmIdentity record={job} />
        ) : (
          <>
            <div className="report-title-with-origin">
              <ReportOrigin value={job.report_origin} />
              <strong>{reportTitle(job)}</strong>
            </div>
            <ReportTimeNote />
            <ReportScope job={job} />
          </>
        )}
        <div className="head-actions">
          <span>
            작업 실행 <Badge status={str(job.status) || null} />
          </span>
          <span>
            공개 결과{' '}
            <Badge
              status={
                job.deletion != null
                  ? 'deleted'
                  : job.result_ref != null
                    ? str(result.result_status, 'unknown')
                    : 'unpublished'
              }
            />
          </span>
          <span>
            현재 시도 {typeof job.attempt_no === 'number' ? job.attempt_no : '미확인'} ·{' '}
            {str(job.stage, '단계 미확인')}
          </span>
          {keyButton('job', '작업 ID')}
        </div>
        <small>
          작업 {str(job.id)} · 접수 {formatDate(str(job.created_at))}
        </small>
        <label className="field">
          <span>확인할 실행 시도</span>
          <select
            value={selected ? String(selected.attempt_no) : ''}
            onChange={(e) => {
              setRelationKey('');
              setKnowledgeIndex(null);
              updateEvidence('', Number(e.target.value));
            }}
          >
            {!selected && (
              <option value="">
                {requestedAttempt !== null ? '요청한 시도가 응답에 없음' : '실행 시도 없음'}
              </option>
            )}
            {attempts.map((a) => (
              <option key={String(a.attempt_no)} value={String(a.attempt_no)}>
                {String(a.attempt_no)}회차{a.attempt_no === job.attempt_no ? ' · 현재' : ' · 과거'}{' '}
                · {str(a.stage, '단계 미확인')} · {formatDate(str(a.started_at))}
              </option>
            ))}
          </select>
        </label>
        <details className="debug-pinned" open={tab === 'input'}>
          <summary>
            접수 시 고정된 입력·설정
            {trace
              ? ` · 사건 revision ${trace.evidence_version ?? '해당 없음'} · 모델 revision ${obj(versions.model).model_revision ?? '미기록'} · 지식 ${Array.isArray(versions.knowledge) ? `${knowledge.length}건` : '미기록'}`
              : ''}
          </summary>
          <QueryState query={traceQuery}>
            {traceQuery.data && !trace ? (
              <Notice tone="warning">
                작업 연결 불일치: 다른 작업의 고정 설정은 표시하지 않습니다.
              </Notice>
            ) : (
              <>
                <p>
                  작업 접수 당시 고정된 값입니다. 현재 서비스 설정과 다를 수 있으며, 모델 키는 실제
                  호출 성공을 뜻하지 않습니다. 지식은 선택 전 후보를 포함합니다.
                </p>
                <div className="head-actions">
                  {keyButton(
                    job.kind === 'rca' ? 'snapshot' : 'request',
                    job.kind === 'rca' ? '사건 입력 원본' : '보고서 요청 원본',
                  )}
                  {keyButton('model', '고정 모델 버전')}
                </div>
                <DataView
                  value={{
                    model: versions.model ?? '미기록',
                    execution_profile_revision: versions.execution_profile_revision ?? '미기록',
                  }}
                />
                {knowledge.length > 0 && (
                  <details>
                    <summary>고정된 지식 후보 {knowledge.length}건</summary>
                    <div className="head-actions">
                      {knowledge.map((k, index) => (
                        <button
                          className="button"
                          key={`${str(k.knowledge_id)}-${String(k.revision)}`}
                          onClick={() => {
                            setRelationKey('');
                            updateEvidence('');
                            setKnowledgeIndex(index);
                          }}
                        >
                          지식 {index + 1} · revision {String(k.revision ?? '미기록')}
                        </button>
                      ))}
                    </div>
                  </details>
                )}
                {!knowledge.length && (
                  <p>
                    고정된 지식 버전 기록이 없습니다. 사용 여부는 선택한 시도의 Runbook 기록에서
                    확인하세요.
                  </p>
                )}
                <RawRecord value={versions} label="고정된 버전·계산 기준 원본" />
                <div className="head-actions">
                  <Link
                    className="button"
                    to="/settings/models"
                    state={{ from: location.pathname + location.search }}
                  >
                    현재 모델 설정
                  </Link>
                  <Link
                    className="button"
                    to="/knowledge"
                    state={{ from: location.pathname + location.search }}
                  >
                    현재 Runbook 목록
                  </Link>
                </div>
              </>
            )}
          </QueryState>
        </details>
      </section>
      <nav className="debug-tabs" aria-label="작업 상세 구분">
        {debugTabs.map(([key, label, question]) => {
          const next = new URLSearchParams(contextParams);
          next.set('tab', key);
          return (
            <Link
              key={key}
              to={`?${next}`}
              state={location.state}
              aria-current={tab === key ? 'page' : undefined}
            >
              <b>{label}</b>
              <small>{question}</small>
            </Link>
          );
        })}
      </nav>
      <div className={`debug-layout ${relation ? 'has-inspector' : ''}`}>
        <section
          className="panel live-padding stack debug-content"
          aria-label={debugTabs.find(([key]) => key === tab)?.[1]}
        >
          {tab === 'input' && (
            <>
              <h2>접수된 분석 조건</h2>
              <p>
                이 작업 API에 보존된 대상과 기간입니다. 현재 설정으로 다시 계산한 값이 아닙니다.
              </p>
              <DataView
                reportDisplay={job.kind === 'report'}
                value={Object.fromEntries(
                  [
                    'target',
                    'scope',
                    'time_range',
                    'timezone',
                    'purpose_ids',
                    'topic_ids',
                    'group_by',
                    'topic_group_by',
                    'comparison_range',
                    'symptom',
                  ]
                    .filter((k) => job[k] != null)
                    .map((k) => [k, job[k]]),
                )}
              />
              <h3>입력의 출처 따라가기</h3>
              <div className="head-actions">
                {job.kind === 'rca' ? (
                  <>
                    {keyButton('incident', '원본 사건')}
                    {keyButton('snapshot', '실행 당시 사건 스냅샷')}
                  </>
                ) : (
                  keyButton('request', '즉시 요청·정기 회차')
                )}
                {job.parent_job_id != null && keyButton('parent', '이전 작업')}
              </div>
              <QueryState query={traceQuery}>
                {trace && (
                  <>
                    <InputTrace trace={trace} />
                    <JobComparison job={job} trace={trace} from={from} />
                  </>
                )}
              </QueryState>
              <details>
                <summary>RCA·보고서 처리 흐름 안내</summary>
                <WorkflowGuide kind={str(job.kind)} />
              </details>
            </>
          )}
          {tab === 'execution' && (
            <>
              <h2>실행 시도</h2>
              <p>
                <code>job_attempts(job_id, attempt_no)</code>로 구분합니다. 과거 시도를 선택해도
                근거·데이터 탭도 선택한 시도의 기록을 표시합니다. 공개 결과는 바뀌지 않습니다.
              </p>
              {attempt !== null && <AttemptComparison attempts={attempts} attempt={attempt} />}
              {selected ? (
                <>
                  <details>
                    <summary>선택한 시도 상세</summary>
                    <DataView value={selected} fieldNames={{ ended_at: '실행 종료' }} />
                  </details>
                  <RawRecord value={selected} />
                </>
              ) : (
                <Notice>
                  제공된 시도 기록이 없습니다. queued 상태는 아직 실행되지 않았을 수 있습니다.
                </Notice>
              )}
              {keyButton('attempt', '선택한 시도')}
              <h3>작업 전체 상태</h3>
              <DataView
                reportDisplay={job.kind === 'report'}
                value={Object.fromEntries(
                  [
                    'status',
                    'stage',
                    'queue_reason',
                    'termination_reason',
                    'deadline_at',
                    'cancel_requested_at',
                  ].map((k) => [k, job[k]]),
                )}
              />
              <div className="head-actions">
                {job.can_cancel === true && (
                  <button className="button danger" onClick={() => onAction('cancel')}>
                    취소 요청
                  </button>
                )}
                {job.can_retry === true && (
                  <button className="button" onClick={() => onAction('retry')}>
                    재시도
                  </button>
                )}
              </div>
              <p className="muted">
                작업 상태와 시도 기록을 대조하세요. Worker·lease·heartbeat 원문과 실시간 내부 단계
                추적은 현재 API에 없습니다.
              </p>
            </>
          )}
          {tab === 'evidence' && (
            <>
              <h2>조회 요청·응답과 판단 근거</h2>
              {evidenceAttempt !== null && (
                <Notice>
                  선택한 시도 {evidenceAttempt}의 저장 기록입니다. 화면 위에서 시도를 변경할 수
                  있습니다. 조회 이름을 누르면 요청 인자와 응답 snapshot을 확인합니다. 수집 성공과
                  분석 근거 충분성은 별개입니다.
                </Notice>
              )}
              {evidenceAttempt !== null ? (
                <StoredEvidence
                  key={`${str(job.id)}-${evidenceAttempt}`}
                  job={job}
                  attempt={evidenceAttempt}
                  onEvidence={onEvidence}
                />
              ) : (
                <Notice>유효한 시도를 선택해야 근거를 조회할 수 있습니다.</Notice>
              )}
            </>
          )}
          {tab === 'result' && (
            <>
              <h2>결과와 공개 상태</h2>
              {job.deletion == null && keyButton('result', '공개 결과 키')}
              {job.deletion != null ? (
                <ReportDeletionNotice job={job} />
              ) : job.result_ref == null ? (
                <Notice>
                  아직 공개된 결과가 없습니다. 미공개 후보는 이 화면에서 제공하지 않습니다.
                </Notice>
              ) : (
                <>
                  <details>
                    <summary>발행 결과가 기록한 버전·계산 기준 원본</summary>
                    <DataView value={result.versions} />
                  </details>
                  {job.kind === 'report' ? (
                    <>
                      <ReportExports id={str(job.id)} />
                      <ReportContent
                        key={`${str(job.id)}:${str(job.result_ref)}`}
                        value={result}
                        request={job}
                        onEvidence={onEvidence}
                      />
                      <Link
                        className="button"
                        to={`/reports/new?parent_job_id=${encodeURIComponent(str(job.id))}`}
                      >
                        새 조건으로 보고서 요청
                      </Link>
                    </>
                  ) : (
                    <RcaResult job={job} onEvidence={onEvidence} showEvidence={false} />
                  )}
                </>
              )}
              {job.deletion == null && (
                <Reviews
                  id={str(job.id)}
                  subject="job"
                  target={obj(job.target)}
                  reportDisplay={job.kind === 'report'}
                />
              )}
            </>
          )}
        </section>
        {relation && (
          <RecordInspector
            onEvidence={onEvidence}
            relation={relation}
            onClose={() => {
              setKnowledgeIndex(null);
              setRelationKey('');
              updateEvidence('');
            }}
          />
        )}
      </div>
    </>
  );
}
