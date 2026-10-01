import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import {
  debugTab,
  debugTabs,
  evidenceRelation,
  jobRelation,
  knowledgeRelation,
  returnPath,
} from '../lib/debug';
import { obj, rows, str, useResource, type Row } from '../lib/live';
import { ReportOrigin, ReportTimeNote } from './ReportMeta';
import { formatDate } from '../lib/domain';
import { reportScope, reportTitle } from '../lib/workflow';
import { Reviews, ReportExports } from '../pages/Results';
import { AlarmIdentity, DataView, QueryState } from './live';
import { Badge, Notice } from './ui';
import { RcaResult } from './RcaDebug';
import { InputTrace, StoredEvidence, JobComparison, RawRecord } from './TraceView';
import { ReportContent } from './ReportContent';
import { RecordInspector } from './RecordInspector';
import { WorkflowGuide } from './WorkflowGuide';

export function JobDebug({ job, onAction }: { job: Row; onAction: (action: string) => void }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const contextParams = new URLSearchParams(params);
  const from = params.get('from') || location.state?.from || location.state?.reportList;
  if (from) contextParams.set('from', returnPath(from));
  const tab = debugTab(params.get('tab'));
  const attempts = rows(job.attempts);
  const requestedAttempt = params.get('attempt');
  const attempt = requestedAttempt === null ? job.attempt_no : Number(requestedAttempt);
  const selected = attempts.find((a) => a.attempt_no === attempt);
  const [relationKey, setRelationKey] = useState('');
  const [evidenceId, setEvidenceId] = useState('');
  const [inspectedAttempt, setInspectedAttempt] = useState(0);
  const [knowledgeIndex, setKnowledgeIndex] = useState<number | null>(null);
  const result = job.result_ref != null ? obj(job.result) : {};
  const traceQuery = useResource(`/jobs/${encodeURIComponent(str(job.id))}/trace`);
  const trace = traceQuery.data;
  const evidenceAttempt =
    typeof attempt === 'number' && Number.isInteger(attempt) && attempt >= 0 ? attempt : 0;
  const knowledge = rows(obj(result.versions).knowledge);
  const relation =
    knowledgeIndex !== null && knowledge[knowledgeIndex]
      ? knowledgeRelation(knowledge[knowledgeIndex])
      : evidenceId
        ? evidenceRelation({ ...job, attempt_no: inspectedAttempt }, evidenceId, true)
        : relationKey
          ? jobRelation(job, relationKey, typeof attempt === 'number' ? attempt : undefined, trace)
          : null;
  const inspect = (key: string) => {
    setKnowledgeIndex(null);
    setEvidenceId('');
    setRelationKey(key);
  };
  const onEvidence = (id: string) => {
    setInspectedAttempt(tab === 'result' ? Number(job.attempt_no ?? 0) : evidenceAttempt);
    setKnowledgeIndex(null);
    setRelationKey('');
    setEvidenceId(id);
  };
  const keyButton = (key: string, label: string) => (
    <button className="button" onClick={() => inspect(key)} aria-expanded={relationKey === key}>
      {label} · 연결 정보
    </button>
  );
  return (
    <>
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
            <span>{reportScope(job)}</span>
          </>
        )}
        <div className="head-actions">
          <span>
            작업 실행 <Badge status={str(job.status) || null} />
          </span>
          <span>
            공개 결과{' '}
            <Badge
              status={job.result_ref != null ? str(result.result_status, 'unknown') : 'unpublished'}
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
              <label className="field">
                <span>확인할 실행 시도</span>
                <select
                  value={selected ? String(selected.attempt_no) : ''}
                  onChange={(e) => {
                    const next = new URLSearchParams(contextParams);
                    next.set('attempt', e.target.value);
                    setParams(next, { state: location.state });
                  }}
                >
                  {!selected && (
                    <option value="">
                      {requestedAttempt ? '요청한 시도가 응답에 없음' : '실행 시도 없음'}
                    </option>
                  )}
                  {attempts.map((a) => (
                    <option key={String(a.attempt_no)} value={String(a.attempt_no)}>
                      {String(a.attempt_no)}회차 · {formatDate(str(a.started_at))} ·{' '}
                      {str(a.stage, '단계 미확인')}
                    </option>
                  ))}
                </select>
              </label>
              {selected ? (
                <>
                  <DataView value={selected} fieldNames={{ ended_at: '실행 종료' }} />
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
              <Notice>
                선택한 시도 {evidenceAttempt}의 저장 기록입니다. 실행·시도 탭에서 시도를 변경할 수
                있습니다. 조회 이름을 누르면 요청 인자와 응답 snapshot을 확인합니다. 수집 성공과
                분석 근거 충분성은 별개입니다.
              </Notice>
              <StoredEvidence
                key={`${str(job.id)}-${evidenceAttempt}`}
                job={job}
                attempt={evidenceAttempt}
                onEvidence={onEvidence}
              />
            </>
          )}
          {tab === 'result' && (
            <>
              <h2>결과와 공개 상태</h2>
              {keyButton('result', '공개 결과 키')}
              {job.result_ref == null ? (
                <Notice>
                  아직 공개된 결과가 없습니다. 미공개 후보는 이 화면에서 제공하지 않습니다.
                </Notice>
              ) : (
                <>
                  <h3>실행에 고정된 설정·지식</h3>
                  <div className="head-actions">
                    {keyButton('model', '모델 설정 버전')}
                    {knowledge.map((k, index) => (
                      <button
                        className="button"
                        key={`${str(k.knowledge_id)}-${String(k.revision)}`}
                        onClick={() => {
                          setRelationKey('');
                          setEvidenceId('');
                          setKnowledgeIndex(index);
                        }}
                      >
                        지식 {index + 1} · revision {String(k.revision ?? '미제공')} 연결 정보
                      </button>
                    ))}
                  </div>
                  <details>
                    <summary>적용된 버전·계산 기준 원본</summary>
                    <DataView value={result.versions} />
                  </details>
                  {job.kind === 'report' ? (
                    <>
                      <ReportExports id={str(job.id)} />
                      <ReportContent value={result} request={job} onEvidence={onEvidence} />
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
              <Reviews
                id={str(job.id)}
                subject="job"
                target={obj(job.target)}
                reportDisplay={job.kind === 'report'}
              />
            </>
          )}
        </section>
        {relation && (
          <RecordInspector
            relation={relation}
            onClose={() => {
              setKnowledgeIndex(null);
              setRelationKey('');
              setEvidenceId('');
            }}
          />
        )}
      </div>
    </>
  );
}
