import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import { ArrowRight, FileText, Search, Terminal, X } from 'lucide-react';
import { useApp } from '../lib/store';
import {
  canonical,
  obj,
  queryPath,
  rows,
  strings,
  str,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { debugPath } from '../lib/debug';
import { reportTitle } from '../lib/workflow';
import { rcaReasons } from '../lib/rcaLabels';
import { reportReason } from '../lib/report';
import { aggregateReasons } from '../components/AggregateReport';
import { reportReceivedRange } from '../lib/reportPeriod';
import { AlarmIdentity, More, QueryState } from '../components/live';
import { Badge } from '../components/ui';
import { ReportOrigin, ReportPeriod, ReportScope } from '../components/ReportMeta';
import { NewWorkspace, incidentTitle, summaryState, targetLabel } from './NewWorkspace';
import { ReportFilters } from './Reports';
import './console.css';

const encoded = (value: unknown) => encodeURIComponent(str(value));

export function ConsoleWorkspace() {
  const app = useApp(),
    location = useLocation();
  if (app.mode === 'workbench')
    return ['/dashboard', '/jobs'].includes(location.pathname) ? <DeveloperConsole /> : <Outlet />;
  // Unified console: Ops 보고서 keeps the former Ops console pages; RCA and job pages stay classic.
  if (location.pathname === '/jobs') return <Navigate to="/cases" replace />;
  if (location.pathname === '/reports') return <OperatorConsole />;
  return /^\/(reports|schedules)(\/|$)/.test(location.pathname) ? <NewWorkspace /> : <Outlet />;
}

export function DebugRunList({
  items,
  from,
  selected,
  onSelect,
}: {
  items: Row[];
  from: string;
  selected?: string;
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="console-table-wrap">
      <table className="console-table">
        <caption className="sr-only">작업별 실행 상태와 디버깅 진입점</caption>
        <thead>
          <tr>
            <th>작업 / 대상</th>
            <th>실행 · 발행</th>
            <th>단계 · 종료 사유</th>
            <th>접수 · 진단</th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={str(j.id)} data-selected={selected === j.id || undefined}>
              <td>
                <span className="console-kind">{j.kind === 'report' ? 'OPS' : 'RCA'}</span>
                <Link className="console-run-id" to={debugPath(str(j.id), 'execution', from)}>
                  {str(j.id)}
                </Link>
                {j.kind === 'report' ? (
                  <>
                    <span>{reportTitle(j)}</span>
                    <ReportScope job={j} />
                  </>
                ) : (
                  <AlarmIdentity record={j} />
                )}
              </td>
              <td>
                <Badge status={str(j.status) || null} />
                <div className="console-cell-note">
                  {j.result_ref ? (
                    <Badge status={str(j.result_status) || 'unknown'} />
                  ) : (
                    '결과 미발행'
                  )}
                </div>
                {!!j.queue_reason && (
                  <small>{labels[str(j.queue_reason)] || str(j.queue_reason)}</small>
                )}
              </td>
              <td>
                <strong>{str(j.stage, '단계 미기록')}</strong>
                <small>
                  {rcaReasons[str(j.termination_reason)] ||
                    str(j.termination_reason, '종료 사유 미기록')}
                </small>
              </td>
              <td>
                <time>{formatDate(str(j.created_at))}</time>
                <small>시도 {typeof j.attempt_no === 'number' ? j.attempt_no : '미확인'}</small>
                {onSelect ? (
                  <button
                    className="button"
                    aria-label={`${str(j.id)} 진단 보기`}
                    id={`console-select-${encoded(j.id)}`}
                    aria-controls="console-diagnosis"
                    aria-pressed={selected === j.id}
                    onClick={() => onSelect(str(j.id))}
                  >
                    진단 보기
                  </button>
                ) : (
                  <Link to={debugPath(str(j.id), 'execution', from)}>실행 기록 →</Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeveloperConsole() {
  const app = useApp(),
    location = useLocation(),
    navigate = useNavigate();
  const [params, setParams] = useSearchParams(),
    [jobId, setJobId] = useState('');
  const failureView = location.pathname === '/dashboard';
  const status = params.has('status') ? params.get('status') || '' : failureView ? 'failed' : '';
  const received = reportReceivedRange(params);
  const scopeKey = canonical(app.scope);
  const previousScope = useRef(scopeKey);
  const inspect = previousScope.current === scopeKey ? params.get('inspect') || '' : '';
  useEffect(() => {
    if (previousScope.current === scopeKey) return;
    previousScope.current = scopeKey;
    if (params.has('inspect')) {
      const next = new URLSearchParams(params);
      next.delete('inspect');
      setParams(next, { replace: true });
    }
  }, [scopeKey, params, setParams]);
  const diagnosisHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!inspect) return;
    diagnosisHeading.current?.focus({ preventScroll: true });
    if (window.innerWidth <= 1250) diagnosisHeading.current?.scrollIntoView({ block: 'start' });
  }, [inspect]);
  const selectedJob = useResource(inspect ? `/jobs/${encoded(inspect)}` : null, undefined, true);
  const q = useList(
    app.canOperate && !received.error
      ? queryPath('/jobs', {
          scope: app.scope,
          kind: params.get('kind') || '',
          status,
          node: params.get('node') || '',
          incident_id: params.get('incident_id') || '',
          from: received.from,
          to: received.to,
          limit: 30,
        })
      : null,
    true,
  );
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (key !== 'inspect') next.delete('inspect');
    if (value || key === 'status') next.set(key, value);
    else next.delete(key);
    setParams(next);
  };
  const from = location.pathname + location.search;
  const open = (event: FormEvent) => {
    event.preventDefault();
    if (jobId.trim()) navigate(debugPath(jobId.trim(), 'execution', from));
  };
  return (
    <div className="console-page">
      <header className="console-heading">
        <div>
          <span className="console-kicker">
            <Terminal size={15} /> DEVELOPMENT
          </span>
          <h1 tabIndex={-1}>{failureView ? '실패 진단' : '전체 작업'}</h1>
          <p>노드와 접수 시각으로 작업을 찾고, 멈춘 단계와 당시 기록을 확인합니다.</p>
        </div>
        <form className="console-id-search" onSubmit={open}>
          <label htmlFor="console-job-id">작업 ID로 바로 열기</label>
          <div>
            <input
              id="console-job-id"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="Job UUID"
              required
            />
            <button className="button primary" type="submit">
              <Search size={16} /> 열기
            </button>
          </div>
        </form>
      </header>
      <div className={`console-developer-layout${inspect ? ' has-selection' : ''}`}>
        <section className="console-surface" aria-labelledby="run-list-title">
          <header className="console-section-head">
            <h2 id="run-list-title">작업 기록</h2>
            <span>접수 최신순 · 자동 갱신</span>
          </header>
          <div className="console-filters">
            <label>
              종류{' '}
              <select
                aria-label="작업 종류"
                value={params.get('kind') || ''}
                onChange={(e) => filter('kind', e.target.value)}
              >
                <option value="">전체</option>
                <option value="rca">RCA</option>
                <option value="report">Ops</option>
              </select>
            </label>
            <label>
              실행 상태{' '}
              <select
                aria-label="실행 상태"
                value={status}
                onChange={(e) => filter('status', e.target.value)}
              >
                <option value="">전체</option>
                {[
                  'queued',
                  'running',
                  'retry_wait',
                  'succeeded',
                  'failed',
                  'cancelled',
                  'expired',
                ].map((s) => (
                  <option key={s} value={s}>
                    {labels[s]}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button"
              onClick={() => setParams(failureView ? { status: '' } : {})}
              disabled={!params.toString() && !failureView}
            >
              필터 해제
            </button>
            <span className="console-count">
              {q.isError ? '조회 실패' : q.isPending ? '조회 중' : `불러온 ${q.items.length}건`}
            </span>
          </div>
          <form
            className="console-filters console-search-filters"
            key={`${params.get('node')}-${params.get('incident_id')}`}
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget),
                next = new URLSearchParams(params);
              for (const key of ['node', 'incident_id']) {
                const value = String(values.get(key) || '').trim();
                if (value) next.set(key, value);
                else next.delete(key);
              }
              next.delete('inspect');
              setParams(next);
            }}
          >
            <label>
              노드 이름 또는 UID
              <input
                name="node"
                defaultValue={params.get('node') || ''}
                placeholder="dgx-node-07"
              />
            </label>
            <label>
              사건 ID
              <input
                name="incident_id"
                defaultValue={params.get('incident_id') || ''}
                placeholder="사건 UUID (선택)"
              />
            </label>
            <button className="button" type="submit">
              작업 찾기
            </button>
          </form>
          <DateFilter prefix="received" label="접수" />
          {received.error ? (
            <p role="alert" className="live-padding">
              {received.error}
            </p>
          ) : (
            <>
              <QueryState
                query={q}
                empty={!q.items.length}
                emptyTitle="조건에 맞는 작업이 없습니다."
                emptyDescription="필터와 관측 범위를 확인하거나 작업 ID로 직접 조회하세요."
              >
                <DebugRunList
                  items={q.items}
                  from={from}
                  selected={inspect}
                  onSelect={(id) => filter('inspect', id)}
                />
              </QueryState>
              <More query={q} />
            </>
          )}
        </section>
        {inspect && (
          <aside
            className="console-diagnostics console-surface"
            aria-label="선택한 작업 진단"
            id="console-diagnosis"
          >
            <header className="console-section-head">
              <h2 ref={diagnosisHeading} tabIndex={-1}>
                선택한 작업
              </h2>
              <button
                className="icon-button"
                aria-label="작업 진단 닫기"
                onClick={() => {
                  filter('inspect', '');
                  document.getElementById(`console-select-${encoded(inspect)}`)?.focus();
                }}
              >
                <X size={18} />
              </button>
            </header>
            <QueryState query={selectedJob}>
              {selectedJob.data && <RunDiagnosis job={selectedJob.data} from={from} />}
            </QueryState>
          </aside>
        )}
      </div>
      <details className="console-connections">
        <summary>현재 서비스·설정 점검</summary>
        <p>실행 당시 고정된 설정은 작업 상세에서 확인합니다.</p>
        <div className="console-connection-links">
          <ConsoleLink
            to="/settings/backend"
            title="서비스 상태"
            text="Backend · Incident · Job Controller"
          />
          <ConsoleLink
            to="/settings/models"
            title="모델 연결"
            text="추론 서버와 역할별 모델 설정"
          />
          <ConsoleLink
            to="/settings/data"
            title="관측 데이터"
            text="클러스터 · Grafana · 데이터소스"
          />
          <ConsoleLink to="/knowledge" title="Runbook" text="분석 지침과 발행된 revision" />
        </div>
      </details>
    </div>
  );
}

function RunDiagnosis({ job, from }: { job: Row; from: string }) {
  const attempts = rows(job.attempts);
  const latest = attempts.find((a) => a.attempt_no === job.attempt_no);
  const reason = str(latest ? latest.termination_reason : job.termination_reason);
  return (
    <div className="console-diagnosis-body">
      <code>{str(job.id)}</code>
      <Badge status={str(job.status) || 'unknown'} />
      {job.kind === 'report' ? <ReportScope job={job} /> : <AlarmIdentity record={job} />}
      <dl>
        <dt>저장된 단계</dt>
        <dd>{str(latest?.stage, str(job.stage, '미기록'))}</dd>
        <dt>종료 사유</dt>
        <dd>{rcaReasons[reason] || reason || '미기록'}</dd>
        <dt>현재 시도</dt>
        <dd>{typeof job.attempt_no === 'number' ? `${job.attempt_no}회차` : '미기록'}</dd>
      </dl>
      {job.queue_reason != null && <p>{labels[str(job.queue_reason)] || str(job.queue_reason)}</p>}
      <div className="console-record-links">
        {(['input', 'execution', 'evidence', 'result'] as const).map((tab, i) => (
          <Link key={tab} to={debugPath(str(job.id), tab, from)}>
            {
              [
                '고정 입력·설정',
                '시도 비교·오류',
                '수집 근거·원문',
                job.result_ref ? '발행 결과' : '결과 미발행',
              ][i]
            }
          </Link>
        ))}
      </div>
      {!!job.incident_id && (
        <Link className="text-link" to={`/incidents/${encoded(job.incident_id)}`} state={{ from }}>
          연결 사건 보기 →
        </Link>
      )}
      <p className="muted">
        선택한 시도의 기록을 상세에서 대조하세요. 공개 결과는 마지막 발행본입니다.
      </p>
    </div>
  );
}

function DateFilter({ prefix, label }: { prefix: string; label: string }) {
  const [params, setParams] = useSearchParams();
  return (
    <form
      className="console-date-filter"
      key={`${params.get(`${prefix}_from`)}-${params.get(`${prefix}_to`)}`}
      onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget),
          next = new URLSearchParams(params);
        next.delete('inspect');
        for (const key of [`${prefix}_from`, `${prefix}_to`]) {
          const value = String(values.get(key) || '');
          if (value) next.set(key, value);
          else next.delete(key);
        }
        setParams(next);
      }}
    >
      <label>
        {label} 시작일
        <input
          type="date"
          name={`${prefix}_from`}
          defaultValue={params.get(`${prefix}_from`) || ''}
        />
      </label>
      <label>
        {label} 종료일
        <input type="date" name={`${prefix}_to`} defaultValue={params.get(`${prefix}_to`) || ''} />
      </label>
      <button className="button" type="submit">
        {label}일 적용
      </button>
      <button
        className="button"
        type="button"
        disabled={!params.has(`${prefix}_from`) && !params.has(`${prefix}_to`)}
        onClick={() => {
          const next = new URLSearchParams(params);
          next.delete('inspect');
          next.delete(`${prefix}_from`);
          next.delete(`${prefix}_to`);
          setParams(next);
        }}
      >
        {label} 기간 해제
      </button>
      <small>
        {label === '분석'
          ? '선택한 날짜와 분석 기간이 겹치는 보고서'
          : '종료일 포함 · 비워 두면 전체 기간'}{' '}
        · 한국 시간
      </small>
    </form>
  );
}

function ConsoleLink({ to, title, text }: { to: string; title: string; text: string }) {
  return (
    <Link className="console-destination" to={to}>
      <div>
        <b>{title}</b>
        <span>{text}</span>
      </div>
      <ArrowRight size={16} />
    </Link>
  );
}

export function OperatorIncidentList({ items, from }: { items: Row[]; from: string }) {
  return (
    <div className="console-incidents">
      {items.map((i) => {
        const published = obj(obj(i.rca_summary).latest_published);
        return (
          <article className="console-incident" key={str(i.id)}>
            <div className="console-incident-state">
              <Badge status={str(i.state) || 'unknown'} />
            </div>
            <div className="console-incident-body">
              <h3>
                <Link to={`/incidents/${encoded(i.id)}`} state={{ from }}>
                  {incidentTitle(i)}
                </Link>
              </h3>
              <p className="console-target">{targetLabel(i)}</p>
              <div className="console-cell-note">
                발생 {formatDate(str(i.occurred_at, str(i.first_seen)))} · 검토{' '}
                {labels[str(i.review_status)] || '미확인'}
              </div>
            </div>
            <div className="console-incident-result">
              <span>최근 조사 · {summaryState(i)}</span>
              {published.job_id ? (
                <>
                  <span>
                    발행 결과 · <Badge status={str(published.result_status) || 'unknown'} />
                  </span>
                  <Link
                    className="button"
                    to={`/incidents/${encoded(i.id)}?analysis=${encoded(published.job_id)}`}
                    state={{ from }}
                  >
                    RCA 확인·처리 <ArrowRight size={15} />
                  </Link>
                  <Link
                    className="text-link"
                    to={`/incidents/${encoded(i.id)}#new-incident-state`}
                    state={{ from }}
                  >
                    처리 상태·기록 →
                  </Link>
                </>
              ) : (
                <>
                  <span className="muted">
                    {i.rca_summary ? '발행된 RCA 없음' : '발행 여부 미확인'}
                  </span>
                  <Link className="text-link" to={`/incidents/${encoded(i.id)}`} state={{ from }}>
                    사건·진행 확인 →
                  </Link>
                </>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function OperatorReportList({
  items,
  from,
  compact = false,
}: {
  items: Row[];
  from: string;
  compact?: boolean;
}) {
  return (
    <div className="console-report-list">
      {items.map((j) => (
        <article className="console-report" key={str(j.id)}>
          <div className="console-report-icon">
            <FileText size={24} />
          </div>
          <div className="console-report-body">
            <ReportOrigin value={j.report_origin} />
            <h3>
              <Link to={`/reports/${encoded(j.id)}`} state={{ from }}>
                {reportTitle(j)}
              </Link>
            </h3>
            <ReportPeriod value={j.time_range} />
            <ReportScope job={j} />
            {!!j.result_ref &&
              !j.deletion &&
              (compact ? (
                <details className="c2-report-preview">
                  <summary>저장된 주요 변화·한계 보기</summary>
                  <ReportPreview value={obj(j.report_preview)} />
                </details>
              ) : (
                <ReportPreview value={obj(j.report_preview)} />
              ))}
          </div>
          <div className="console-report-result">
            <Badge status={str(j.status) || 'unknown'} />
            {j.result_ref && !j.deletion ? (
              <Badge status={str(j.result_status) || 'unknown'} />
            ) : (
              <span>{j.deletion ? '삭제된 보고서' : '결과 미발행'}</span>
            )}
            <Link className="button" to={`/reports/${encoded(j.id)}`} state={{ from }}>
              {j.deletion ? '삭제 기록' : j.result_ref ? '보고서 읽기' : '작성 현황'}{' '}
              <ArrowRight size={15} />
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}

function ReportPreview({ value }: { value: Row }) {
  const summaries = rows(value.summaries),
    limits = strings(value.limitations),
    missing = strings(value.missing_inputs);
  return (
    <div className="console-report-preview">
      {summaries.length ? (
        <>
          <b>
            {value.narrative_status === 'failed' && value.method === 'partial_interpretation'
              ? '일부 주제 AI 해석·계산 요약'
              : value.narrative_status === 'complete' && value.method === 'llm_interpreted'
                ? 'AI 해석 요약'
                : value.narrative_status === 'complete' && value.method === 'llm_prioritized'
                  ? 'AI가 고른 주요 변화'
                  : value.method === 'deterministic_fallback'
                    ? '계산 결과 요약'
                    : '저장된 주요 변화'}
            {value.truncated === true ? ' · 발췌' : ''}
          </b>
          <ul>
            {summaries.map((s, i) => (
              <li key={i}>{str(s.text)}</li>
            ))}
          </ul>
        </>
      ) : (
        <p className="muted">목록 요약 없음 · 보고서에서 수치와 해석을 확인하세요.</p>
      )}
      {(limits.length > 0 || missing.length > 0) && (
        <details>
          <summary>관측·해석 한계 {limits.length + missing.length}개</summary>
          <ul>
            {limits.map((s, i) => (
              <li key={`l${i}`}>{s}</li>
            ))}
            {missing.map((s, i) => (
              <li key={`m${i}`}>{aggregateReasons[s] || reportReason(s)}</li>
            ))}
          </ul>
        </details>
      )}
      {value.truncated === true && <small>요약 일부만 표시 · 전체 내용은 본문에서 확인</small>}
    </div>
  );
}

export function OperatorConsole({ compact = false }: { compact?: boolean }) {
  const app = useApp(),
    location = useLocation(),
    [params, setParams] = useSearchParams();
  const reportsOnly = location.pathname === '/reports',
    casesOnly = location.pathname === '/cases';
  const caseStatus = ['unclosed', 'open', 'acknowledged', 'closed', 'all'].includes(
    params.get('status') || '',
  )
    ? params.get('status')!
    : 'unclosed';
  const received = reportReceivedRange(params);
  const analysis = reportReceivedRange(params, 'analysis', '분석');
  const occurred = reportReceivedRange(params, 'occurred', '발생');
  const filterOccurrences = casesOnly && caseStatus !== 'unclosed';
  const incidents = useList(
    app.canOperate && !reportsOnly && (!filterOccurrences || !occurred.error)
      ? queryPath('/incidents', {
          scope: app.scope,
          from: filterOccurrences ? occurred.from : undefined,
          to: filterOccurrences ? occurred.to : undefined,
          status: casesOnly ? (caseStatus === 'all' ? '' : caseStatus) : 'unclosed',
          limit: casesOnly ? 30 : 8,
        })
      : null,
    true,
  );
  const reports = useList(
    app.canOperate && !casesOnly && (!reportsOnly || (!received.error && !analysis.error))
      ? queryPath('/reports', {
          scope: app.scope,
          limit: reportsOnly ? 30 : 4,
          status: reportsOnly
            ? params.get('status') || (params.get('tab') === 'final' ? 'succeeded' : '')
            : '',
          topic_id: reportsOnly ? params.get('topic') || '' : '',
          from: reportsOnly ? received.from : undefined,
          to: reportsOnly ? received.to : undefined,
          analysis_from: reportsOnly ? analysis.from : undefined,
          analysis_to: reportsOnly ? analysis.to : undefined,
        })
      : null,
    true,
  );
  const from = location.pathname + location.search;
  return (
    <div className="console-page">
      <header className="console-heading">
        <div>
          <span className="console-kicker">GPU OPERATIONS</span>
          <h1 tabIndex={-1}>{reportsOnly ? 'Ops 보고서' : casesOnly ? 'RCA 사건' : '운영 개요'}</h1>
          <p>
            {reportsOnly
              ? '분석 대상일로 보고서를 찾고, 주요 변화와 관측 한계를 확인합니다.'
              : '남아 있는 사건을 확인하고, RCA 판단과 후속 처리 기록을 이어갑니다.'}
          </p>
        </div>
        {!casesOnly && (
          <div className="head-actions">
            {reportsOnly && params.toString() && (
              <button className="button" onClick={() => setParams({})}>
                모든 조건 해제
              </button>
            )}
            <Link className="button" to="/schedules">
              자동 보고서 설정
            </Link>
            <Link className="button primary" to="/reports/new">
              보고서 만들기 <ArrowRight size={16} />
            </Link>
          </div>
        )}
      </header>
      {!reportsOnly && (
        <section className="console-surface" aria-labelledby="incident-list-title">
          <header className="console-section-head">
            <div>
              <h2 id="incident-list-title">
                {!casesOnly || caseStatus === 'unclosed' ? '미종결 사건' : '사건 이력'}
              </h2>
              <p>
                {!casesOnly || caseStatus === 'unclosed'
                  ? '열림·확인됨 사건 · 발생일 제한 없음'
                  : '선택한 처리 상태와 발생일의 사건'}{' '}
                · 알림 해제는 사건 종결과 다릅니다.
              </p>
            </div>
            {!casesOnly && (
              <Link to="/cases" className="text-link">
                미종결 사건 더 보기 →
              </Link>
            )}
          </header>
          {casesOnly && (
            <div className="console-filters">
              <label>
                처리 상태{' '}
                <select
                  aria-label="사건 처리 상태"
                  value={caseStatus}
                  onChange={(e) => {
                    const next = new URLSearchParams(params);
                    if (e.target.value === 'unclosed') {
                      next.delete('occurred_from');
                      next.delete('occurred_to');
                    }
                    if (e.target.value) next.set('status', e.target.value);
                    else next.delete('status');
                    setParams(next);
                  }}
                >
                  <option value="unclosed">미종결 · 열림·확인됨</option>
                  <option value="all">전체 이력</option>
                  {['open', 'acknowledged', 'closed'].map((s) => (
                    <option key={s} value={s}>
                      {labels[s]}
                    </option>
                  ))}
                </select>
              </label>
              <span className="console-count">접수 최신순 · 불러온 {incidents.items.length}건</span>
            </div>
          )}
          {filterOccurrences && <DateFilter prefix="occurred" label="발생" />}
          {filterOccurrences && occurred.error ? (
            <p role="alert" className="live-padding">
              {occurred.error}
            </p>
          ) : (
            <>
              <QueryState
                query={incidents}
                empty={!incidents.items.length}
                emptyTitle={
                  !casesOnly || caseStatus === 'unclosed'
                    ? '조회된 미종결 사건이 없습니다.'
                    : '조건에 맞는 사건이 없습니다.'
                }
                emptyDescription="처리 상태·발생일·관측 범위를 확인하세요. 사건이 없다는 것만으로 장비 정상 여부를 판단할 수 없습니다."
              >
                <OperatorIncidentList items={incidents.items} from={from} />
              </QueryState>
              {casesOnly && <More query={incidents} />}
            </>
          )}
          {!casesOnly && (
            <div className="console-section-foot">
              <Link to="/cases?status=all">종결 사건을 포함한 전체 이력 →</Link>
            </div>
          )}
        </section>
      )}
      {!casesOnly && (
        <section className="console-surface" aria-labelledby="report-list-title">
          <header className="console-section-head">
            <div>
              <h2 id="report-list-title">기간별 Ops 보고서</h2>
              <p>접수 최신순 · 분석 기간은 각 보고서에 표시됩니다.</p>
            </div>
            {!reportsOnly && (
              <Link className="text-link" to="/reports">
                전체 보고서 →
              </Link>
            )}
          </header>
          {reportsOnly && (
            <>
              <DateFilter prefix="analysis" label="분석" />
              <details
                className="console-secondary-filters"
                open={
                  params.has('status') ||
                  params.has('topic') ||
                  params.has('received_from') ||
                  params.has('received_to') ||
                  undefined
                }
              >
                <summary>상태·주제·요청 접수일 조건</summary>
                <ReportFilters resetLabel="상태·접수 조건 해제" />
              </details>
            </>
          )}
          {reportsOnly && (received.error || analysis.error) ? (
            <p role="alert" className="live-padding">
              {analysis.error || received.error}
            </p>
          ) : (
            <QueryState
              query={reports}
              empty={!reports.items.length}
              emptyTitle="조회된 보고서가 없습니다."
              emptyDescription="필터를 확인하거나 ‘보고서 만들기’에서 분석 기간과 범위를 선택하세요."
            >
              <OperatorReportList items={reports.items} from={from} compact={compact} />
            </QueryState>
          )}
          {reportsOnly && <More query={reports} />}
        </section>
      )}
      <div className="console-reading-note">
        <b>결과를 읽을 때</b>
        <span>
          부분 산출·근거 부족은 원인 확정을 뜻하지 않습니다. 보고서 안에서 누락된 자료와 추가 확인
          사항을 읽고 검토를 남기세요.
        </span>
        <Link to="/operator-guide">읽기 안내 →</Link>
      </div>
    </div>
  );
}
