import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Badge, Field, Modal, Notice, PageHead, Panel } from '../components/ui';
import { AlarmIdentity, CommandError, DataView, More, QueryState } from '../components/live';
import {
  num,
  queryPath,
  rows,
  str,
  strings,
  useCommand,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { RcaJobSummary } from '../components/RcaDebug';
import { reportRequestTime } from '../lib/reportPeriod';
import {
  ReportExecution,
  ReportOrigin,
  ReportTimeNote,
  ReportPeriod,
  ReportScope,
} from '../components/ReportMeta';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
import { reportReturnPath } from '../lib/reportNavigation';
import { obj } from '../lib/live';
import { groupLabel, topicName } from '../lib/report';
import { reportScopeClusters, reportTitle, reportTopics } from '../lib/workflow';
import { JobDebug } from '../components/JobDebug';
import { debugPath, returnPath } from '../lib/debug';
export function Jobs() {
  const app = useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const [jobId, setJobId] = useState('');
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind') || '',
    status = params.get('status') || '';
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  };
  const setKind = (value: string) => filter('kind', value),
    setStatus = (value: string) => filter('status', value);
  const q = useList(
    app.ready ? queryPath('/jobs', { scope: app.scope, kind, status, limit: 30 }) : null,
    true,
  );
  return (
    <div className="page jobs-workspace">
      <PageHead
        eyebrow=""
        title={app.mode === 'developer' ? '작업 디버깅' : '작업 이력'}
        description="작업의 진행 상태와 결과 품질을 확인하세요. 보고서 제목은 보고서 화면으로 연결됩니다. 실행 기록은 작업 상태·시도 이력에서 확인하세요."
      />
      {app.mode === 'developer' && (
        <form
          className="live-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            if (jobId.trim())
              navigate(debugPath(jobId.trim(), 'input', location.pathname + location.search));
          }}
        >
          <Field label="작업 ID로 바로 열기">
            <input
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="로그에 기록된 job_id"
              required
            />
          </Field>
          <button className="button" disabled={!jobId.trim()}>
            작업 열기
          </button>
        </form>
      )}
      <Panel
        title={kind || status ? '조건에 맞는 작업' : '전체 작업'}
        description="실행 상태는 처리 진행 상황, 결과 품질은 분석 근거의 충족 정도입니다."
      >
        <div className="live-toolbar">
          <Field label="작업 종류">
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">전체</option>
              <option value="rca">RCA 조사</option>
              <option value="report">운영 분석 보고서</option>
            </select>
          </Field>
          <Field label="실행 상태">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              {[
                'queued',
                'running',
                'retry_wait',
                'succeeded',
                'failed',
                'cancelled',
                'expired',
              ].map((v) => (
                <option key={v} value={v}>
                  {labels[v] || v}
                </option>
              ))}
            </select>
          </Field>
          {(kind || status) && (
            <button
              className="button"
              onClick={() => {
                const next = new URLSearchParams(params);
                next.delete('kind');
                next.delete('status');
                setParams(next);
              }}
            >
              필터 초기화
            </button>
          )}
        </div>
        {!q.isPending && !q.isError && (
          <div className="jobs-list-summary">
            <span>
              현재 표시 {q.items.length}건{q.hasNextPage ? ' · 아래에서 더 보기' : ''}
            </span>
            {q.dataUpdatedAt > 0 && (
              <span>마지막 조회 {reportRequestTime(new Date(q.dataUpdatedAt).toISOString())}</span>
            )}
          </div>
        )}
        <QueryState
          query={q}
          empty={!q.items.length}
          emptyTitle="조건에 맞는 작업이 없습니다."
          emptyDescription="선택한 클러스터와 작업 종류·실행 상태를 확인하세요. 필터를 적용했다면 초기화할 수 있습니다."
        >
          <JobHistoryTable items={q.items} />
        </QueryState>
        <More query={q} />
      </Panel>
    </div>
  );
}
export function JobHistoryTable({ items }: { items: Row[] }) {
  const location = useLocation();
  const from = location.pathname + location.search;
  return (
    <div className="table-wrap jobs-table-wrap">
      <table className="jobs-history-table">
        <caption className="sr-only">작업별 실행 상태, 결과 품질과 접수 시각</caption>
        <colgroup>
          <col className="jobs-title-col" />
          <col />
          <col />
          <col className="jobs-time-col" />
          <col className="jobs-action-col" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">작업 · 대상</th>
            <th scope="col">실행 상태</th>
            <th scope="col">결과 품질</th>
            <th scope="col">접수 시각</th>
            <th scope="col">보기</th>
          </tr>
        </thead>
        <tbody>
          {items.map((job) => {
            const id = str(job.id);
            const isReport = job.kind === 'report';
            const target = obj(job.target);
            const clusters = reportScopeClusters(job);
            const namespaces = clusters.every((c) => c.namespaces === '전체 Namespace')
              ? '전체 Namespace'
              : clusters.some((c) => c.namespaces === 'Namespace 범위 미확인')
                ? 'Namespace 범위 미확인'
                : '클러스터별 Namespace 범위';
            return (
              <tr key={id}>
                <td>
                  <Link
                    className="text-link jobs-title"
                    to={
                      isReport || job.result_ref != null
                        ? `/${job.kind === 'rca' ? 'analyses' : 'reports'}/${id}#final-report`
                        : `/jobs/${id}`
                    }
                    state={{ from }}
                  >
                    {isReport ? (
                      reportTitle(job)
                    ) : job.kind === 'rca' ? (
                      <AlarmIdentity record={job} compact />
                    ) : (
                      str(job.title, id)
                    )}
                  </Link>
                  <div className="jobs-identity">
                    <span>
                      {isReport
                        ? '운영 분석 보고서'
                        : job.kind === 'rca'
                          ? 'RCA 조사'
                          : str(job.kind)}
                    </span>
                    {isReport && <ReportOrigin value={job.report_origin} />}
                  </div>
                  <p className="jobs-scope-summary">
                    {isReport
                      ? clusters.length
                        ? `클러스터 ${clusters.length}개 · ${namespaces}`
                        : '분석 대상 미확인'
                      : job.kind === 'rca'
                        ? `클러스터 ${str(target.cluster_id) || str(job.cluster_id) || '미확인'} · Namespace ${str(target.namespace) || '미확인'}`
                        : '대상 미확인'}
                  </p>
                  <details className="jobs-request-details">
                    <summary>대상·요청 조건 보기</summary>
                    {isReport ? (
                      <>
                        <ReportScope job={job} />
                        <p>
                          <strong>분석 주제</strong> {reportTopics(job)}
                        </p>
                        <div>
                          <strong>분석 대상 기간</strong>
                          <ReportPeriod value={job.time_range} />
                        </div>
                        <p>
                          <strong>요청 집계</strong> {groupLabel(job.group_by, job.topic_group_by)}
                        </p>
                      </>
                    ) : (
                      <>
                        {job.kind === 'rca' && <AlarmIdentity record={job} />}
                        <p>마지막 기록 단계 · {executionLabel(job.stage)}</p>
                      </>
                    )}
                    <p className="jobs-id">작업 ID · {id}</p>
                  </details>
                </td>
                <td className="job-state-cell">
                  <Badge status={str(job.status) || 'unknown'} />
                </td>
                <td className="job-state-cell">
                  <Badge status={str(job.result_status) || null} />
                </td>
                <td className="job-received-time">
                  {reportRequestTime(str(job.created_at)).replace(/ (?=\d{2}:)/, '\n')}
                </td>
                <td>
                  {job.result_ref != null ? (
                    <Link
                      className="text-link jobs-result-link"
                      state={{ from }}
                      to={`/${job.kind === 'rca' ? 'analyses' : 'reports'}/${id}#final-report`}
                    >
                      결과 보기
                    </Link>
                  ) : (
                    <span className="jobs-unpublished">결과 미발행</span>
                  )}
                  <div>
                    <Link
                      className="text-link jobs-result-link"
                      to={`/jobs/${id}`}
                      state={{ from }}
                    >
                      작업 상태·시도 이력
                    </Link>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function JobDetail() {
  const location = useLocation();
  const from = returnPath(
    new URLSearchParams(location.search).get('from') || location.state?.from,
    obj(location.state).reportList ? reportReturnPath(location.state) : '/jobs',
  );
  const { id } = useParams(),
    app = useApp(),
    q = useResource(id ? `/jobs/${id}` : null, undefined, true),
    cmd = useCommand();
  const [action, setAction] = useState(''),
    [reason, setReason] = useState('');
  const j = q.data || {};
  const act = async (e: FormEvent) => {
    e.preventDefault();
    if (
      await cmd.run(
        `/jobs/${id}/${action}`,
        { reason: reason.trim() },
        { version: num(j.version), idempotent: true },
      )
    ) {
      setAction('');
      setReason('');
      app.notify(
        action === 'cancel'
          ? '취소 요청을 접수했습니다. 최종 상태는 서버 응답으로 확인합니다.'
          : '재시도 요청을 접수했습니다.',
      );
    }
  };
  const reportView = j.kind === 'report' && app.mode !== 'developer';
  return (
    <div className={reportView ? 'page report-job-detail' : 'page'}>
      <PageHead
        eyebrow={reportView ? '운영 분석 보고서 · 작업 상세' : 'JOB DETAIL'}
        title={app.mode === 'developer' ? '작업 디버깅' : reportView ? reportTitle(j) : '작업 상세'}
        description={reportView ? `작업 ID · ${id || '미확인'}` : id || ''}
        actions={
          <Link className="button" to={from} state={{ reportRow: obj(location.state).reportRow }}>
            {from === '/jobs' ? '작업 목록' : '이전 목록·기록으로'}
          </Link>
        }
      />
      <QueryState query={q}>
        {app.mode === 'developer' ? (
          <JobDebug
            key={id}
            job={j}
            onAction={(next) => {
              cmd.setError('');
              setAction(next);
            }}
          />
        ) : (
          <>
            {j.kind === 'report' && <ReportTimeNote />}
            <Panel
              title={j.kind === 'report' ? '실행 상태와 시도 이력' : '실행 상태'}
              className={j.kind === 'report' ? 'report-job-execution' : ''}
              action={j.kind === 'report' ? <ReportOrigin value={j.report_origin} /> : undefined}
            >
              <div className="live-padding stack">
                <div className="head-actions">
                  {j.kind === 'report' ? (
                    <div className="report-job-status">
                      <div>
                        <span>실행 상태</span>
                        <Badge status={str(j.status) || 'unknown'} />
                      </div>
                      <div>
                        <span>결과 품질</span>
                        <Badge status={str(j.result_status) || 'unknown'} />
                      </div>
                      <div>
                        <span>현재 시도</span>
                        <strong>
                          {typeof j.attempt_no === 'number'
                            ? j.attempt_no === 0
                              ? '아직 시작 전'
                              : `${j.attempt_no}차`
                            : '미확인'}
                        </strong>
                      </div>
                      <div>
                        <span>마지막 기록 단계</span>
                        <strong>{executionLabel(j.stage)}</strong>
                      </div>
                    </div>
                  ) : (
                    <>
                      <Badge status={str(j.status)} />
                      <Badge status={str(j.result_status) || null} />
                      <span>
                        시도 {num(j.attempt_no)} · {str(j.stage, '단계 미확인')}
                      </span>
                    </>
                  )}
                </div>
                {j.kind === 'report' && <ReportAttempts job={j} />}
                {j.kind === 'rca' && <RcaJobSummary job={j} />}
                <dl className="details">
                  <dt>{j.kind === 'report' ? '요청 접수 시각' : '접수 시각'}</dt>
                  <dd>
                    {j.kind === 'report'
                      ? reportRequestTime(str(j.created_at))
                      : formatDate(str(j.created_at))}
                  </dd>
                  {j.kind === 'report' && (
                    <>
                      <dt>분석 대상 기간</dt>
                      <dd>
                        <ReportPeriod value={j.time_range} />
                      </dd>
                    </>
                  )}
                  <dt>실행 시각</dt>
                  <dd>
                    {j.kind === 'report'
                      ? reportRequestTime(str(j.started_at))
                      : formatDate(str(j.started_at))}
                  </dd>
                  {j.kind === 'report' && (
                    <>
                      <dt>보고서 실행시간</dt>
                      <dd>
                        <ReportExecution job={j} />
                      </dd>
                    </>
                  )}
                  <dt>기한</dt>
                  <dd>
                    {j.kind === 'report'
                      ? reportRequestTime(str(j.deadline_at))
                      : formatDate(str(j.deadline_at))}
                  </dd>
                  <dt>종료 사유</dt>
                  <dd>
                    {j.kind === 'report'
                      ? executionLabel(j.termination_reason)
                      : str(j.termination_reason, '—')}
                  </dd>
                </dl>
                {j.queue_reason != null && (
                  <Notice>{labels[str(j.queue_reason)] || str(j.queue_reason)}</Notice>
                )}
                {j.cancel_requested_at != null && j.status === 'running' && (
                  <Notice>취소 요청 처리 중 · {formatDate(str(j.cancel_requested_at))}</Notice>
                )}
                <div className="head-actions">
                  {j.can_cancel === true && (
                    <button
                      className="button danger"
                      onClick={() => {
                        cmd.setError('');
                        setAction('cancel');
                      }}
                    >
                      취소 요청
                    </button>
                  )}
                  {j.can_retry === true && (
                    <button
                      className="button"
                      onClick={() => {
                        cmd.setError('');
                        setAction('retry');
                      }}
                    >
                      재시도
                    </button>
                  )}
                  {j.result_ref != null && (
                    <Link
                      className="button primary"
                      state={location.state}
                      to={`/${j.kind === 'report' ? 'reports' : 'analyses'}/${id}${j.kind === 'report' ? '#final-report' : ''}`}
                    >
                      저장된 결과 보기
                    </Link>
                  )}
                  {j.parent_job_id != null && (
                    <Link className="button" to={`/jobs/${str(j.parent_job_id)}`}>
                      이전 작업
                    </Link>
                  )}
                </div>
              </div>
            </Panel>
            {j.kind === 'report' ? (
              <ReportJobRequest job={j} />
            ) : (
              <>
                <Panel title="요청 조건">
                  <div className="live-padding">
                    <DataView
                      reportDisplay={j.kind === 'report'}
                      value={Object.fromEntries(
                        [
                          'scope',
                          'target',
                          'time_range',
                          'timezone',
                          'purpose_ids',
                          'topic_ids',
                          'group_by',
                          'topic_group_by',
                          'comparison_range',
                          'symptom',
                        ]
                          .filter((k) => j[k] != null)
                          .map((k) => [k, j[k]]),
                      )}
                    />
                  </div>
                </Panel>
                <Panel title="시도 이력">
                  <div className="live-padding">
                    <DataView reportDisplay={j.kind === 'report'} value={j.attempts} />
                  </div>
                </Panel>
              </>
            )}
          </>
        )}
      </QueryState>
      {action && (
        <Modal
          title={action === 'cancel' ? '작업 취소 요청' : '작업 재시도'}
          onClose={() => {
            if (!cmd.busy) setAction('');
          }}
        >
          <form className="stack" onSubmit={act}>
            <Notice>서버가 현재 버전과 변경 가능 여부를 다시 확인합니다.</Notice>
            <Field label="사유">
              <textarea required value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
            <CommandError error={cmd.error} />
            <button className="button primary" disabled={cmd.busy || !reason.trim()}>
              {cmd.busy ? '처리 중…' : '요청 보내기'}
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}

const executionLabels: Record<string, string> = {
  validating: '입력 검증',
  workflow: '자료 수집·분석',
  saving: '결과 저장',
  completing: '완료 처리',
  complete: '처리 완료',
  timeout: '시간 초과',
  transient_error: '일시적 오류',
  dependency_unavailable: '연결 서비스 사용 불가',
  invalid_input: '입력 검증 실패',
  invalid_result: '결과 검증 실패',
};
function executionLabel(value: unknown) {
  const code = str(value);
  return executionLabels[code] || labels[code] || code || '미확인';
}
function ReportAttempts({ job }: { job: Row }) {
  const attempts = rows(job.attempts).sort((a, b) => num(b.attempt_no) - num(a.attempt_no));
  return (
    <section className="report-job-attempts" aria-label="시도 이력">
      <h3>
        시도 이력 <span>최근 시도부터</span>
      </h3>
      {attempts.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>시도</th>
                <th>시작 시각</th>
                <th>종료 시각</th>
                <th>마지막 단계</th>
                <th>종료 사유</th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((a, i) => (
                <tr key={i}>
                  <th scope="row">
                    {typeof a.attempt_no === 'number' ? `${a.attempt_no}차` : '미확인'}
                    {a.attempt_no === job.attempt_no && <small>현재 회차</small>}
                  </th>
                  <td>{reportRequestTime(str(a.started_at))}</td>
                  <td>
                    {a.ended_at
                      ? reportRequestTime(str(a.ended_at))
                      : a.attempt_no === job.attempt_no && job.status === 'running'
                        ? '실행 중'
                        : '종료 기록 없음'}
                  </td>
                  <td title={str(a.stage)}>{executionLabel(a.stage)}</td>
                  <td title={str(a.termination_reason)}>{executionLabel(a.termination_reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>
          {Array.isArray(job.attempts) && job.attempt_no === 0
            ? '아직 실행을 시작하지 않아 시도 이력이 없습니다.'
            : '시도 이력 미확인 · 서버에 기록된 내역을 확인할 수 없습니다.'}
        </p>
      )}
      <details>
        <summary>시도 원본 기록</summary>
        <DataView reportDisplay value={job.attempts} />
      </details>
    </section>
  );
}
function ReportJobRequest({ job }: { job: Row }) {
  const ids = strings(job.topic_ids);
  const groups = obj(job.topic_group_by);
  return (
    <Panel title="분석 대상과 주제">
      <div className="live-padding stack">
        <ReportScope job={job} />
        <section className="report-job-topics" aria-label="요청한 분석 주제">
          <h3>요청한 분석 주제{ids.length > 0 && ` · ${ids.length}개`}</h3>
          <p>
            요청한 내용입니다. 주제별 산출 여부와 근거 부족 사유는 완성된 보고서에서 확인하세요.
          </p>
          {ids.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>분석 주제</th>
                    <th>주제 ID</th>
                    <th>요청 집계 기준</th>
                  </tr>
                </thead>
                <tbody>
                  {ids.map((id, i) => (
                    <tr key={i}>
                      <th scope="row">{/^O(0[1-9]|1[01])$/.test(id) ? topicName(id) : id}</th>
                      <td>{id}</td>
                      <td>{groupLabel(job.topic_group_by != null ? groups[id] : job.group_by)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Notice>분석 주제 미확인</Notice>
          )}
        </section>
        <details>
          <summary>요청 조건 원본</summary>
          <DataView
            reportDisplay
            value={Object.fromEntries(
              [
                'scope',
                'time_range',
                'timezone',
                'topic_ids',
                'group_by',
                'topic_group_by',
                'comparison_range',
              ]
                .filter((k) => job[k] != null)
                .map((k) => [k, job[k]]),
            )}
          />
        </details>
      </div>
    </Panel>
  );
}
