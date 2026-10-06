import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Badge, Field, Modal, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, DataView, JobRows, More, QueryState } from '../components/live';
import { num, queryPath, str, useCommand, useList, useResource } from '../lib/live';
import { RcaJobSummary } from '../components/RcaDebug';
import { reportRequestTime } from '../lib/reportPeriod';
import {
  ReportExecution,
  ReportOrigin,
  ReportTimeNote,
  ReportPeriod,
} from '../components/ReportMeta';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
import { reportReturnPath } from '../lib/reportNavigation';
import { obj } from '../lib/live';
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
    <div className="page">
      <PageHead
        eyebrow="JOB HISTORY"
        title={app.mode === 'developer' ? '작업 디버깅' : '작업 이력'}
        description="서버에 접수된 작업의 실행 상태와 결과 품질을 확인합니다."
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
      <Panel title="전체 작업">
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
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
        <QueryState query={q} empty={!q.items.length}>
          <JobRows items={q.items} />
        </QueryState>
        <More query={q} />
      </Panel>
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
  return (
    <div className="page">
      <PageHead
        eyebrow="JOB DETAIL"
        title={app.mode === 'developer' ? '작업 디버깅' : '작업 상세'}
        description={id || ''}
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
            <Panel title="실행 상태">
              <div className="live-padding stack">
                <div className="head-actions">
                  {j.kind === 'report' && <ReportOrigin value={j.report_origin} />}
                  <Badge status={str(j.status)} />
                  <Badge status={str(j.result_status) || null} />
                  <span>
                    시도 {num(j.attempt_no)} · {str(j.stage, '단계 미확인')}
                  </span>
                </div>
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
                  <dd>{formatDate(str(j.started_at))}</dd>
                  {j.kind === 'report' && (
                    <>
                      <dt>보고서 실행시간</dt>
                      <dd>
                        <ReportExecution job={j} />
                      </dd>
                    </>
                  )}
                  <dt>기한</dt>
                  <dd>{formatDate(str(j.deadline_at))}</dd>
                  <dt>종료 사유</dt>
                  <dd>{str(j.termination_reason, '—')}</dd>
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
                      to={`/${j.kind === 'report' ? 'reports' : 'analyses'}/${id}`}
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
