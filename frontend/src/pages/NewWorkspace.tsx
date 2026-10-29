import { gapMeaning } from '../lib/rcaGuidance';
import { rcaReasons } from '../lib/rcaLabels';
import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, CalendarClock, FileText, ScanSearch } from 'lucide-react';
import { Badge, Empty, Field, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, More, QueryState } from '../components/live';
import { AggregateReport } from '../components/AggregateReport';
import { ReportStatements } from '../components/ReportContent';
import { BasicReport, ReportChecks } from '../components/BasicReport';
import { RcaEvidenceDialog } from '../components/RcaEvidenceDialog';
import { RcaNarrative } from '../components/RcaNarrative';
import { ReportOrigin, ReportPeriod, ReportScope } from '../components/ReportMeta';
import { ReportDeleteButton, ReportDeletionNotice } from '../components/ReportDeletion';
import { useApp } from '../lib/store';
import {
  num,
  obj,
  queryPath,
  rows,
  str,
  strings,
  useCommand,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { reportTitle } from '../lib/workflow';
import { reportReceivedRange } from '../lib/reportPeriod';
import {
  metricName,
  metricTarget,
  metricUnit,
  metricValue,
  reportReason,
  topicName,
} from '../lib/report';
import { ReportFilters } from './Reports';
import { downloadReader } from '../lib/readerExport';
import { AggregateReportForm } from './AggregateReportForm';
import { Schedules } from './Schedules';
import { NewReviews } from './NewReviews';
import { ReportExports } from './Results';
import './new-workspace.css';

export const incidentTitle = (i: Row) =>
  str(obj(i.target).reason) ||
  str(obj(i.target).title) ||
  str(i.title) ||
  str(i.symptom) ||
  '사건 이름 미확인';
export const targetLabel = (i: Row) =>
  [
    str(i.cluster_id) || str(obj(i.target).cluster_id),
    str(obj(i.target).namespace),
    str(obj(i.target).node) || str(obj(i.target).k8s_node_name),
    str(obj(i.target).pod_name) || str(obj(i.target).pod),
  ]
    .filter(Boolean)
    .join(' / ') || '대상 이름 미확인';
export function summaryState(incident: Row) {
  if (!Object.hasOwn(incident, 'rca_summary') || !incident.rca_summary) return '분석 요약 미확인';
  const summary = obj(incident.rca_summary),
    latest = obj(summary.latest_job);
  if (!summary.latest_job) return '조사 기록 없음';
  return labels[str(latest.status)] || '조사 상태 미확인';
}
function Status({ job }: { job: Row }) {
  return (
    <div className="new-status">
      <span>
        진행 <Badge status={str(job.status) || null} />
      </span>
      <span>
        결과 <Badge status={job.result_ref ? str(job.result_status) || null : null} />
      </span>
    </div>
  );
}
function Back({ fallback = '/cases' }: { fallback?: string }) {
  const location = useLocation();
  const from = str(obj(location.state).from);
  const safe = /^\/(dashboard|cases|reports|incidents|analyses|schedules)(?:[/?#]|$)/.test(from);
  const destination = safe ? from : fallback;
  const [section, id] = destination.split(/[?#]/)[0].split('/').filter(Boolean);
  const label =
    section === 'dashboard'
      ? '운영 현황'
      : section === 'cases'
        ? '사건 목록'
        : section === 'incidents'
          ? '사건 상세'
          : section === 'analyses'
            ? '저장된 사건 분석'
            : section === 'schedules'
              ? id
                ? '자동 보고서 일정 상세'
                : '자동 보고서 설정 목록'
              : id === 'new'
                ? '보고서 만들기'
                : id
                  ? '보고서 상세'
                  : '보고서 목록';
  return (
    <Link className="text-link new-back" to={destination} state={obj(location.state).returnState}>
      ← {label}
      {label.endsWith('상세') || label.endsWith('만들기') ? '로' : '으로'} 돌아가기
    </Link>
  );
}
function useReturn() {
  const location = useLocation();
  return { from: location.pathname + location.search, returnState: location.state };
}
function IncidentCards({ items }: { items: Row[] }) {
  const back = useReturn();
  return (
    <div className="new-cards">
      {items.map((i) => {
        const published = obj(obj(i.rca_summary).latest_published);
        return (
          <article className="new-case-card" key={str(i.id)}>
            <div>
              <div className="new-status">
                <Badge status={str(i.state, str(i.status)) || null} />
                <span>
                  {i.alarm_status === 'firing'
                    ? '발생 알림 수신'
                    : i.alarm_status === 'resolved'
                      ? '해제 알림 수신'
                      : '알림 상태 미확인'}
                </span>
              </div>
              <h3>
                <Link to={`/incidents/${encodeURIComponent(str(i.id))}`} state={back}>
                  {incidentTitle(i)}
                </Link>
              </h3>
              <p>{targetLabel(i)}</p>
              <small>
                발생 {formatDate(str(i.occurred_at, str(i.first_seen)))} · 접수{' '}
                {formatDate(str(i.created_at))}
              </small>
            </div>
            <div className="new-case-result">
              <span>검토: {labels[str(i.review_status)] || '미확인'}</span>
              <strong>{summaryState(i)}</strong>
              <span>
                {published.job_id
                  ? '공개 결과 있음'
                  : i.rca_summary
                    ? '공개 결과 없음'
                    : '공개 결과 미확인'}
              </span>
              {!!published.job_id && <Badge status={str(published.result_status) || null} />}
              <Link
                className="text-link"
                to={`/incidents/${encodeURIComponent(str(i.id))}`}
                state={back}
              >
                사건 분석 보기 <ArrowRight size={15} />
              </Link>
            </div>
          </article>
        );
      })}
    </div>
  );
}
function ReportCards({ items }: { items: Row[] }) {
  const back = useReturn();
  return (
    <div className="new-report-grid">
      {items.map((j) => (
        <article className="new-report-card" key={str(j.id)}>
          <ReportOrigin value={j.report_origin} />
          <h3>
            <Link to={`/reports/${encodeURIComponent(str(j.id))}`} state={back}>
              {reportTitle(j)}
            </Link>
          </h3>
          <ReportScope job={j} />
          <ReportPeriod value={j.time_range} />
          <Status job={j} />
          <p className="muted">접수 {formatDate(str(j.created_at))}</p>
          <Link className="button" to={`/reports/${encodeURIComponent(str(j.id))}`} state={back}>
            {j.deletion ? '삭제 기록 보기' : j.result_ref ? '보고서 읽기' : '작성 현황 보기'}{' '}
            <ArrowRight size={15} />
          </Link>
        </article>
      ))}
    </div>
  );
}
function Home() {
  const app = useApp();
  const incidents = useList(
    app.ready
      ? queryPath('/incidents', {
          scope: app.scope,
          from: app.timeRange.start,
          to: app.timeRange.end,
          limit: 5,
        })
      : null,
    true,
  );
  const reports = useList(
    app.ready ? queryPath('/reports', { scope: app.scope, limit: 3 }) : null,
    true,
  );
  return (
    <>
      <PageHead
        eyebrow="GPU OPERATIONS"
        title="지금, 확인할 운영 현황"
        description="사건의 원인과 다음 확인 사항을 읽고, 보고서로 운영 변화를 살펴보세요."
        actions={
          <Link className="button primary" to="/reports/new">
            보고서 만들기
          </Link>
        }
      />
      <div className="new-hero">
        <div>
          <span className="new-kicker">하나의 흐름으로</span>
          <h2>
            문제를 이해하고,
            <br />
            다음 판단으로 이어가세요.
          </h2>
          <p>
            조사 완료와 원인 확정은 다릅니다.
            <br />
            확인한 사실과 남은 제한을 함께 제공합니다.
          </p>
        </div>
        <div className="new-shortcuts">
          <Link to="/cases">
            <ScanSearch />
            <span>
              <strong>사건 분석</strong>
              <small>알림 · 원인 · 후속 확인</small>
            </span>
            <ArrowRight />
          </Link>
          <Link to="/reports">
            <FileText />
            <span>
              <strong>운영 보고서</strong>
              <small>기간별 활동 · 변화 · 반복 사건</small>
            </span>
            <ArrowRight />
          </Link>
          <Link to="/schedules">
            <CalendarClock />
            <span>
              <strong>자동 보고서 설정</strong>
              <small>일정과 생성 결과 확인</small>
            </span>
            <ArrowRight />
          </Link>
        </div>
      </div>
      <Panel
        title="최근 접수된 사건"
        description="상단 발생 기간 내 사건 · 최근 접수순"
        action={
          <Link to="/cases" className="text-link">
            사건 목록 보기 →
          </Link>
        }
      >
        <QueryState
          query={incidents}
          empty={!incidents.items.length}
          emptyTitle="조회 기간에 접수된 사건이 없습니다."
          emptyDescription="관측 상태가 정상이라는 의미는 아닙니다. 기간과 범위를 확인하세요."
        >
          <IncidentCards items={incidents.items} />
        </QueryState>
      </Panel>
      <Panel
        title="최근 보고서 요청"
        description="선택한 범위의 최근 요청 · 사건 조회 기간과 별개"
        action={
          <Link to="/reports" className="text-link">
            보고서 목록 보기 →
          </Link>
        }
      >
        <QueryState query={reports} empty={!reports.items.length}>
          <ReportCards items={reports.items} />
        </QueryState>
      </Panel>
    </>
  );
}
function useListPosition(query: ReturnType<typeof useList>) {
  const location = useLocation(),
    restored = useRef('');
  const key = `new-list:${location.pathname}${location.search}`;
  useEffect(() => {
    if (query.isPending || query.isError || restored.current === location.key) return;
    let saved = { count: 0, y: 0 };
    try {
      saved = JSON.parse(sessionStorage.getItem(key) || 'null') || saved;
    } catch {
      /* No position to restore. */
    }
    if (query.items.length < saved.count && query.hasNextPage) {
      if (!query.isFetchingNextPage) void query.fetchNextPage();
      return;
    }
    const frame = requestAnimationFrame(() => {
      window.scrollTo(0, saved.y);
      restored.current = location.key;
    });
    return () => cancelAnimationFrame(frame);
  }, [
    key,
    location.key,
    query.items.length,
    query.hasNextPage,
    query.isPending,
    query.isError,
    query.isFetchingNextPage,
  ]);
  useEffect(() => {
    const save = () => {
      if (restored.current !== location.key) return;
      try {
        sessionStorage.setItem(
          key,
          JSON.stringify({ count: query.items.length, y: window.scrollY }),
        );
      } catch {
        /* Navigation still works. */
      }
    };
    window.addEventListener('scroll', save, { passive: true });
    return () => {
      save();
      window.removeEventListener('scroll', save);
    };
  }, [key, location.key, query.items.length]);
}
function Cases() {
  const app = useApp(),
    [params, setParams] = useSearchParams();
  const status = params.get('status') || '';
  const q = useList(
    app.ready
      ? queryPath('/incidents', {
          scope: app.scope,
          from: app.timeRange.start,
          to: app.timeRange.end,
          status,
          limit: 30,
        })
      : null,
    true,
  );
  useListPosition(q);
  return (
    <>
      <PageHead
        eyebrow="INCIDENTS"
        title="사건 분석"
        description="사건별로 조사 진행 상황과 마지막 공개 결과를 함께 확인하세요."
      />
      <div className="new-toolbar">
        <Field label="처리 상태">
          <select
            value={status}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.set('status', e.target.value);
              setParams(next);
            }}
          >
            {['', 'open', 'acknowledged', 'closed'].map((v) => (
              <option key={v} value={v}>
                {labels[v] || '전체'}
              </option>
            ))}
          </select>
        </Field>
        <p>
          기간은 발생 시각 기준 · 정렬은 최근 접수순
          <br />
          불러온 사건 {q.items.length}건{q.hasNextPage ? ' · 더 보기 가능' : ''}
        </p>
      </div>
      <QueryState query={q} empty={!q.items.length} emptyTitle="조건에 맞는 사건이 없습니다.">
        <IncidentCards items={q.items} />
      </QueryState>
      <More query={q} />
    </>
  );
}
function Incident({ id }: { id: string }) {
  const location = useLocation();
  const q = useResource(`/incidents/${id}`, undefined, true),
    incident = obj(q.data),
    summary = obj(incident.rca_summary),
    published = obj(summary.latest_published),
    latest = obj(summary.latest_job);
  const [historyOpen, setHistoryOpen] = useState(false);
  const history = useList(
    historyOpen ? queryPath('/analyses', { incident_id: id, limit: 10 }) : null,
    true,
  );
  const [params, setParams] = useSearchParams();
  const selected = params.get('analysis') || '';
  const setSelected = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set('analysis', value);
    else next.delete('analysis');
    setParams(next, { preventScrollReset: true, state: location.state });
  };
  const analysis = selected || str(published.job_id);
  const cmd = useCommand(),
    app = useApp();
  return (
    <>
      <Back />
      <PageHead
        eyebrow="INCIDENT ANALYSIS"
        title={incidentTitle(incident)}
        description={targetLabel(incident)}
      />
      <QueryState query={q}>
        <nav className="new-section-nav" aria-label="사건 상세 바로가기">
          <a href="#new-analysis-result">분석 결과 읽기 ↓</a>
          <a href="#new-investigation-history">조사 이력 보기 ↓</a>
          <a href="#new-incident-state">처리 상태 변경 ↓</a>
          <a href="#new-review-records">검토·조치 기록하기 ↓</a>
        </nav>
        <div className="new-detail-meta">
          <div>
            <span>발생 시각</span>
            <strong>{formatDate(str(incident.occurred_at, str(incident.first_seen)))}</strong>
          </div>
          <div>
            <span>사건 처리</span>
            <Badge status={str(incident.state, str(incident.status)) || null} />
          </div>
          <div>
            <span>알림 상태</span>
            <strong>
              {incident.alarm_status === 'resolved'
                ? '해제 알림 수신'
                : incident.alarm_status === 'firing'
                  ? '발생 알림 수신'
                  : '미확인'}
            </strong>
          </div>
          <div>
            <span>최근 조사</span>
            <strong>{summaryState(incident)}</strong>
          </div>
          <div>
            <span>사건 검토</span>
            <strong>{labels[str(incident.review_status)] || '미확인'}</strong>
            <a href="#new-review-records">이 사건의 검토·조치 기록</a>
          </div>
        </div>
        <Notice>
          {selected && selected !== published.job_id
            ? '지정한 조사 결과를 읽고 있습니다. 마지막 공개 결과와 다를 수 있습니다. 사건 기록과 처리 상태는 같은 사건에 연결됩니다.'
            : !incident.rca_summary
              ? '분석 요약을 제공하지 않는 서버입니다. 최신 결과 여부는 미확인입니다.'
              : published.job_id
                ? `마지막 공개 결과를 표시합니다. ${latest.job_id !== published.job_id ? '더 최근 조사는 별도로 진행 상태를 확인하세요.' : '조사 완료가 원인 확정을 뜻하지는 않습니다.'}`
                : '아직 공개된 분석 결과가 없습니다. 진행 상태가 완료여도 공개 전 결과는 표시하지 않습니다.'}
        </Notice>
        <section id="new-analysis-result" tabIndex={-1} aria-label="사건 분석 결과">
          {analysis ? (
            <AnalysisContent key={analysis} id={analysis} incidentId={id} />
          ) : (
            <Empty
              title={summaryState(incident)}
              description="공개 결과가 준비되면 여기에 표시됩니다."
            />
          )}
        </section>
        <section id="new-investigation-history" tabIndex={-1} aria-label="조사 이력">
          <Panel
            title="조사 이력"
            action={
              <button
                className="button"
                aria-expanded={historyOpen}
                onClick={() => setHistoryOpen(!historyOpen)}
              >
                {historyOpen ? '이력 접기' : '이전 조사 보기'}
              </button>
            }
          >
            {historyOpen && (
              <>
                <QueryState query={history} empty={!history.items.length}>
                  <div className="new-history">
                    {history.items.map((j) => (
                      <div key={str(j.id)}>
                        <span>{formatDate(str(j.created_at))}</span>
                        <Status job={j} />
                        {j.result_ref ? (
                          <button
                            className="button"
                            onClick={() => setSelected(str(j.id))}
                            aria-pressed={analysis === j.id}
                          >
                            {analysis === j.id ? '읽는 중' : '이 결과 읽기'}
                          </button>
                        ) : (
                          <span>공개 결과 없음</span>
                        )}
                      </div>
                    ))}
                  </div>
                </QueryState>
                <More query={history} />
              </>
            )}
            {selected && selected !== published.job_id && (
              <button className="button" onClick={() => setSelected('')}>
                마지막 공개 결과로 돌아가기
              </button>
            )}
          </Panel>
        </section>
        <section id="new-incident-state" tabIndex={-1} aria-label="사건 처리 상태 변경">
          <Panel title="사건 처리 상태">
            <p className="live-padding">
              알림 해제, 검토 완료, 사건 종결은 별개입니다. 기록을 저장해도 아래 상태는 바뀌지
              않습니다. <a href="#new-review-records">이 사건에 남긴 기록 확인</a>
            </p>
            <div className="live-padding head-actions">
              {['open', 'acknowledged', 'closed'].map((state) => (
                <button
                  className="button"
                  key={state}
                  disabled={cmd.busy || !app.canOperate || state === incident.state}
                  onClick={async () => {
                    if (
                      await cmd.run(
                        `/incidents/${id}`,
                        { state },
                        { method: 'PATCH', version: num(incident.version) },
                      )
                    )
                      app.notify('처리 상태를 저장했습니다.');
                  }}
                >
                  {labels[state]}
                </button>
              ))}
            </div>
            <div className="live-padding">
              <Field label="검토 상태">
                <select
                  value={str(incident.review_status)}
                  disabled={cmd.busy || !app.canOperate}
                  onChange={async (e) => {
                    if (
                      await cmd.run(
                        `/incidents/${id}`,
                        { review_status: e.target.value },
                        { method: 'PATCH', version: num(incident.version) },
                      )
                    )
                      app.notify('검토 상태를 저장했습니다.');
                  }}
                >
                  <option value="" disabled>
                    미확인
                  </option>
                  {['unreviewed', 'reviewing', 'reviewed'].map((value) => (
                    <option key={value} value={value}>
                      {labels[value] || value}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <CommandError error={cmd.error} />
          </Panel>
        </section>
        <NewReviews
          id={id}
          subject="incident"
          scope={obj(incident.scope)}
          reviewStatus={str(incident.review_status)}
        />
      </QueryState>
    </>
  );
}
function AnalysisContent({ id, incidentId }: { id: string; incidentId?: string }) {
  const modern = useApp().mode === 'operations';
  const [evidence, setEvidence] = useState<string | null>(null);
  const q = useResource(`/analyses/${id}`, undefined, true),
    job = obj(q.data),
    result = obj(job.result);
  const events = rows(obj(obj(result.quality).analysis).error_events);
  const observations = rows(result.device_observations);
  return (
    <QueryState query={q}>
      {incidentId && str(job.incident_id) !== incidentId ? (
        <Notice>
          선택한 분석과 이 사건의 연결을 확인할 수 없습니다. 조사 이력에서 이 사건의 결과를
          선택하세요.
        </Notice>
      ) : (
        <>
          <div className="new-reader">
            <p className="muted">선택한 조사 접수 {formatDate(str(job.created_at))} · 한국 시간</p>
            <ReportScope job={job} />
            {job.time_range != null && <ReportPeriod value={job.time_range} />}
            <Status job={{ ...job, result_status: result.result_status }} />
            {job.result_ref && Object.keys(result).length ? (
              <>
                <RcaNarrative
                  result={result}
                  reader
                  decisionSummary={modern}
                  onEvidence={setEvidence}
                />
                {evidence && <RcaEvidenceDialog id={evidence} onClose={() => setEvidence(null)} />}
                {!rows(result.narrative).length && (
                  <>
                    <Notice>
                      공개된 결과에 설명 본문이 없습니다. 과거 구조화 기록을 표시하며 원인 후보는
                      확정된 원인이 아닙니다.
                    </Notice>
                    <p>{str(result.summary)}</p>
                    <ReportStatements
                      title="저장된 관측 사실"
                      items={rows(result.facts)}
                      metrics={[]}
                    />
                    <ReportStatements
                      title="원인 후보 · 확정 아님"
                      items={rows(result.cause_candidates)}
                      metrics={[]}
                    />
                    <ReportStatements
                      title="권장 확인 · 적용 조건"
                      items={rows(result.recommendations)}
                      metrics={[]}
                      recommendation
                    />
                  </>
                )}
                {strings(result.missing_inputs).length > 0 && (
                  <details>
                    <summary>수집·판정 상세</summary>
                    <strong>충족되지 않은 판단 조건</strong>
                    <ul>
                      {strings(result.missing_inputs).map((code) => (
                        <li key={code}>
                          {gapMeaning(code, result) ||
                            rcaReasons[code] ||
                            '설명되지 않은 조건이 남아 있습니다. 개발자 화면에서 상세 사유를 확인하세요.'}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <details className="new-observations">
                  <summary>관측 원문·처리 상세</summary>
                  {events.length ? (
                    events.map((event, i) => (
                      <article key={i}>
                        <strong>
                          {str(event.error_code, '오류 코드 미기록')} ·{' '}
                          {str(obj(event.target).node, '대상 미확인')}
                        </strong>
                        <p>
                          {formatDate(str(event.event_time))} ·{' '}
                          {event.device_mapping === 'inventory_match'
                            ? '보고된 장치 목록과 연결됨'
                            : '오류 장치 연결 미확정'}
                        </p>
                        <p>
                          목록 연결은 물리적 원인 확정이 아닙니다. 현재 상태와 업무 영향은 별도
                          확인이 필요합니다.
                        </p>
                      </article>
                    ))
                  ) : (
                    <p>별도로 정리된 오류 이벤트가 없습니다. 오류가 없다는 의미는 아닙니다.</p>
                  )}
                  {observations.length > 0 && (
                    <p>
                      상태 보고 {observations.length}건 · 사실 판단에 사용할 수 없는 기록{' '}
                      {observations.filter((o) => o.fact_eligible === false).length}건 · 생산자 시각
                      미확인{' '}
                      {
                        observations.filter((o) => o.producer_time_status === 'missing_or_zero')
                          .length
                      }
                      건. 상태 보고는 오류 이벤트와 별개이며 현재 정상 여부를 뜻하지 않습니다.
                    </p>
                  )}
                  {observations.length > 0 && (
                    <details>
                      <summary>상태 보고의 의미와 제한</summary>
                      {observations.map((o, i) => (
                        <article key={i}>
                          <strong>{str(o.error_code, '오류 코드 미확인')}</strong>
                          <p>
                            {formatDate(str(o.observed_at))} ·{' '}
                            {o.normalized_health === 'unhealthy'
                              ? '이상 상태로 보고됨'
                              : o.normalized_health === 'healthy'
                                ? '정상 상태로 보고됨'
                                : '상태 의미 미확인'}
                          </p>
                          <p>
                            {o.pci_inventory_relation === 'not_in_reported_inventory'
                              ? '오류 장치와 수집 장치 목록이 일치하지 않습니다.'
                              : o.pci_inventory_relation === 'switch_inventory_required'
                                ? '스위치 정보를 별도로 대조해야 합니다.'
                                : '수집 목록 연결만으로 장치 신원과 현재 상태를 확정할 수 없습니다.'}{' '}
                            {o.fact_eligible === false
                              ? '현재 상태 판단에 사용할 조건이 충족되지 않았습니다.'
                              : '관측의 시각과 대상을 함께 확인하세요.'}
                          </p>
                        </article>
                      ))}
                    </details>
                  )}
                  {strings(result.limitations).map((v, i) => (
                    <p key={i}>{reportReason(v)}</p>
                  ))}
                </details>
              </>
            ) : (
              <Empty
                title="공개 결과가 없습니다."
                description="이 조사의 실행 상태와 공개 결과 여부를 구분해 확인하세요."
              />
            )}
          </div>
          {incidentId && (
            <details className="new-observations">
              <summary>이 분석에 남긴 이전 기록 · 사건 기록과 별도</summary>
              <NewReviews id={id} subject="job" scope={obj(job.scope)} readOnly />
            </details>
          )}
        </>
      )}
    </QueryState>
  );
}
function Analysis({ id }: { id: string }) {
  const q = useResource(`/analyses/${id}`, undefined, true),
    job = obj(q.data),
    incidentId = str(job.incident_id);
  const back = useReturn();
  return (
    <>
      <Back />
      <PageHead
        eyebrow="RCA REPORT"
        title="저장된 사건 분석"
        description="선택한 조사의 저장 결과와 당시 범위입니다. 최신 조사 결과나 상단의 현재 선택 범위와 다를 수 있습니다."
      />
      <QueryState query={q}>
        {incidentId ? (
          <Notice>
            사건 검토와 수행한 조치는 원래 사건에 기록합니다.{' '}
            <Link
              to={`/incidents/${encodeURIComponent(incidentId)}?analysis=${encodeURIComponent(id)}#new-review-records`}
              state={back}
            >
              이 RCA를 읽은 사건에서 검토·처리하기
            </Link>
          </Notice>
        ) : (
          <Notice>
            원래 사건의 연결 정보가 없어 사건 기록을 열 수 없습니다. 아래는 이 분석에 남긴 이전
            기록입니다.
          </Notice>
        )}
      </QueryState>
      <AnalysisContent id={id} />
      <details className="new-observations">
        <summary>분석별 이전 기록 보기</summary>
        <NewReviews id={id} subject="job" scope={obj(job.scope)} readOnly />
      </details>
    </>
  );
}
function Reports() {
  const app = useApp(),
    [params] = useSearchParams(),
    received = reportReceivedRange(params);
  const q = useList(
    app.ready && !received.error
      ? queryPath('/reports', {
          scope: app.scope,
          status: params.get('status') || (params.get('tab') === 'final' ? 'succeeded' : ''),
          topic_id: params.get('topic'),
          from: received.from,
          to: received.to,
          limit: 30,
        })
      : null,
    true,
  );
  useListPosition(q);
  return (
    <>
      <PageHead
        eyebrow="REPORTS"
        title="운영 보고서"
        description="기간과 대상을 확인하고 운영 변화를 읽어 보세요. 작성 중인 요청도 함께 표시합니다."
        actions={
          <Link className="button primary" to="/reports/new">
            보고서 만들기
          </Link>
        }
      />
      <ReportFilters />
      {received.error ? (
        <Notice tone="warning">{received.error}</Notice>
      ) : (
        <>
          <p className="muted">접수 시각 최신순 · 불러온 보고서 {q.items.length}건</p>
          <QueryState query={q} empty={!q.items.length}>
            <ReportCards items={q.items} />
          </QueryState>
          <More query={q} />
        </>
      )}
    </>
  );
}
function LegacyReport({ value }: { value: Row }) {
  const topics = rows(value.topics);
  return (
    <section id="final-report" className="new-reader">
      <h2>운영 분석 결과</h2>
      <Notice>
        {value.narrative_status === 'complete'
          ? '확인된 수치를 바탕으로 작성한 설명입니다.'
          : '설명이 미완료이거나 생략된 결과입니다. 저장된 수치와 제한을 확인하세요.'}{' '}
        {reportReason(str(obj(value.quality).narrative_reason))}
      </Notice>
      {str(value.summary) && <p className="new-lead">{str(value.summary)}</p>}
      <ReportChecks topics={topics} />
      <BasicReport topics={topics} />
      {rows(value.narrative).map((n, i) => (
        <section key={i}>
          <h3>{str(n.title, '분석 설명')}</h3>
          <p className="new-prose">{str(n.text)}</p>
        </section>
      ))}
      {topics.map((topic) => (
        <section key={str(topic.topic_id)} id={`topic-${str(topic.topic_id)}`}>
          <h3>
            {topicName(str(topic.topic_id))} <Badge status={str(topic.status) || null} />
          </h3>
          {strings(topic.missing_inputs).map((v) => (
            <p key={v}>{reportReason(v)}</p>
          ))}
          <ReportStatements
            title="확인한 사실"
            items={rows(topic.findings)}
            metrics={rows(topic.metrics)}
          />
          <ReportStatements
            title="운영자 검토 항목"
            items={rows(topic.recommendations)}
            metrics={rows(topic.metrics)}
            recommendation
          />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>지표</th>
                  <th>대상</th>
                  <th>값</th>
                  <th>판단 제한</th>
                </tr>
              </thead>
              <tbody>
                {rows(topic.metrics).map((m, i) => (
                  <tr key={i}>
                    <td>{metricName(str(m.id))}</td>
                    <td>{metricTarget(m)}</td>
                    <td>
                      {metricValue(m)} {metricUnit(m)}
                    </td>
                    <td>
                      {[str(obj(m.quality).reason), ...strings(obj(m.quality).excluded_reasons)]
                        .filter(Boolean)
                        .map(reportReason)
                        .join(' · ') || '별도 제한 기록 없음'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {strings(value.limitations).map((v, i) => (
        <p key={i}>{reportReason(v)}</p>
      ))}
    </section>
  );
}
function ReportActions({ job }: { job: Row }) {
  const cmd = useCommand(),
    app = useApp(),
    [action, setAction] = useState(''),
    [reason, setReason] = useState('');
  return (
    <>
      <div className="head-actions">
        {job.can_cancel === true && (
          <button className="button" onClick={() => setAction('cancel')}>
            생성 취소
          </button>
        )}
        {job.can_retry === true && (
          <button className="button" onClick={() => setAction('retry')}>
            다시 시도
          </button>
        )}
        <ReportDeleteButton job={job} />
      </div>
      {job.cancel_requested_at != null && job.status === 'running' && (
        <Notice>취소 요청을 처리하고 있습니다. 완료 여부는 서버 상태가 바뀐 후 확인하세요.</Notice>
      )}
      {action && (
        <form
          className="new-command"
          data-dirty={!!reason}
          onSubmit={async (e) => {
            e.preventDefault();
            if (
              await cmd.run(
                `/jobs/${str(job.id)}/${action}`,
                { reason: reason.trim() },
                { version: num(job.version) },
              )
            ) {
              setAction('');
              setReason('');
              app.notify('요청을 접수했습니다.');
            }
          }}
        >
          <Field label={action === 'cancel' ? '취소 사유' : '재시도 사유'}>
            <input required value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <button className="button primary" disabled={cmd.busy || !reason.trim()}>
            요청
          </button>
          <button type="button" className="button" onClick={() => setAction('')}>
            닫기
          </button>
        </form>
      )}
      <CommandError error={cmd.error} />
    </>
  );
}
function Report({ id }: { id: string }) {
  const modern = useApp().mode === 'operations';
  const q = useResource(`/reports/${id}`, undefined, true),
    job = obj(q.data),
    result = obj(job.result);
  const aggregatePublished =
    !!job.result_ref &&
    !job.deletion &&
    obj(result.quality).report_format === 'report-aggregate-v1';
  const location = useLocation(),
    navigate = useNavigate();
  const [exportError, setExportError] = useState('');
  const [evidence, setEvidence] = useState<string | null>(null);
  return (
    <>
      <Back fallback="/reports" />
      <PageHead
        eyebrow="OPERATIONS REPORT"
        title={reportTitle(job)}
        description="저장된 기간과 범위의 결과입니다. 이후의 현재 상태와 구분해 읽으세요."
      />
      <QueryState query={q}>
        <div id="new-report-document" className="report-workspace new-report-document">
          <div className="new-detail-meta">
            <ReportScope job={result.scope ? result : job} />
            {(!aggregatePublished || modern) && (
              <ReportPeriod value={result.time_range || job.time_range} />
            )}
            <Status job={{ ...job, result_status: result.result_status }} />
            <ReportOrigin value={job.report_origin} />
          </div>
          {modern ? (
            <details className="c2-report-management">
              <summary>보고서 관리</summary>
              <ReportActions job={job} />
            </details>
          ) : (
            <ReportActions job={job} />
          )}
          {job.deletion ? (
            <ReportDeletionNotice job={job} />
          ) : job.result_ref && Object.keys(result).length ? (
            <>
              <div className="new-print">
                {modern && <ReportExports id={id} />}
                <button
                  className="button"
                  onClick={() => {
                    setExportError('');
                    try {
                      const root = document.getElementById('new-report-document');
                      if (!root) throw new Error('보고서 본문을 확인할 수 없습니다.');
                      downloadReader(root, reportTitle(job));
                    } catch {
                      setExportError(
                        'HTML 파일을 저장하지 못했습니다. 브라우저의 다운로드 설정을 확인하고 다시 시도하세요.',
                      );
                    }
                  }}
                >
                  현재 화면 HTML 저장
                </button>
                <CommandError error={exportError} />
              </div>
              <div
                className={`report-workspace${aggregatePublished ? ' new-report-body' : ''}`}
                onClickCapture={(e) => {
                  const a = (e.target as HTMLElement).closest('a');
                  if (
                    a?.getAttribute('href')?.startsWith('/incidents/') &&
                    !e.ctrlKey &&
                    !e.metaKey &&
                    !e.shiftKey
                  ) {
                    e.preventDefault();
                    e.stopPropagation();
                    navigate(a.getAttribute('href')!, {
                      state: {
                        from: location.pathname + location.search,
                        returnState: location.state,
                      },
                    });
                  }
                }}
              >
                {obj(result.quality).report_format === 'report-aggregate-v1' ? (
                  <AggregateReport
                    value={result}
                    reader={modern}
                    onEvidence={modern ? setEvidence : undefined}
                  />
                ) : (
                  <LegacyReport value={result} />
                )}
              </div>
            </>
          ) : (
            <Empty
              title={labels[str(job.status)] || '작성 상태 미확인'}
              description={
                labels[str(job.queue_reason || job.termination_reason)] ||
                '아직 공개된 결과가 없습니다. 결과가 준비되면 이 화면에 표시됩니다.'
              }
            />
          )}
        </div>
        {evidence && <RcaEvidenceDialog id={evidence} onClose={() => setEvidence(null)} />}
        <NewReviews id={id} subject="job" scope={obj(job.scope)} />
      </QueryState>
    </>
  );
}
function JobRoute({ id }: { id: string }) {
  const q = useResource(`/jobs/${id}`),
    j = obj(q.data),
    location = useLocation();
  return (
    <QueryState query={q}>
      {j.kind === 'report' ? (
        <Navigate replace to={`/reports/${id}`} state={location.state} />
      ) : j.kind === 'rca' ? (
        <Navigate
          replace
          to={j.incident_id ? `/incidents/${str(j.incident_id)}` : `/analyses/${id}`}
          state={location.state}
        />
      ) : (
        <DeveloperOnly />
      )}
    </QueryState>
  );
}
function DeveloperOnly() {
  const app = useApp();
  return (
    <Empty
      title="개발자 화면에서 확인하는 항목입니다."
      description="연결 설정, 원본 관측, 작업 추적은 개발자 화면에서 확인할 수 있습니다."
      action={
        <button className="button" onClick={() => app.setMode('developer')}>
          개발자 화면으로 전환
        </button>
      }
    />
  );
}
export function NewWorkspace() {
  const location = useLocation(),
    navigate = useNavigate(),
    app = useApp(),
    [section, id] = location.pathname.split('/').filter(Boolean);
  useEffect(() => {
    if (!location.hash) return;
    let id: string;
    try {
      id = decodeURIComponent(location.hash.slice(1));
    } catch {
      return;
    }
    const root = document.querySelector('.new-workspace');
    if (!root) return;
    let frame = 0;
    const jump = () => {
      const target = document.getElementById(id);
      if (!target || !root.contains(target)) return false;
      frame = requestAnimationFrame(() => {
        target.scrollIntoView({ block: 'start' });
        target.focus({ preventScroll: true });
      });
      return true;
    };
    const observer = new MutationObserver(() => {
      if (jump()) observer.disconnect();
    });
    if (!jump()) observer.observe(root, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [location.pathname, location.hash, location.key]);
  // Save list scroll by full filter URL; mode switches keep the same location.
  useEffect(() => {
    if (location.hash || ['/cases', '/reports'].includes(location.pathname)) return;
    const key = `new-position:${location.pathname}${location.search}`;
    let previous: string | null = null;
    try {
      previous = sessionStorage.getItem(key);
    } catch {
      /* Storage is optional. */
    }
    const frame = requestAnimationFrame(() => {
      if (previous) window.scrollTo(0, Number(previous));
    });
    const save = () => {
      try {
        sessionStorage.setItem(key, String(window.scrollY));
      } catch {
        /* Storage is optional. */
      }
    };
    window.addEventListener('scroll', save, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', save);
    };
  }, [location.pathname, location.search]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (document.querySelector('form[data-dirty="true"]')) e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);
  let content;
  if (!section) content = <Navigate to="/dashboard" replace />;
  else if (section === 'analyses' && id === 'new') content = <Navigate to="/cases" replace />;
  else if (
    ['fleet', 'jobs', 'knowledge', 'settings'].includes(section) &&
    !(section === 'jobs' && id)
  )
    content = <DeveloperOnly />;
  else if (!app.registeredScope.clusters.length && section !== 'operator-guide')
    content = (
      <Empty
        title="분석할 클러스터가 등록되지 않았습니다."
        description="개발자 화면에서 연결과 클러스터를 등록한 뒤 다시 확인하세요."
        action={
          <button className="button" onClick={() => app.setMode('developer')}>
            개발자 화면으로 전환
          </button>
        }
      />
    );
  else if (section === 'dashboard') content = <Home />;
  else if (section === 'cases') content = <Cases />;
  else if (section === 'incidents' && id) content = <Incident key={id} id={id} />;
  else if (section === 'analyses' && id) content = <Analysis key={id} id={id} />;
  else if (
    section === 'reports' &&
    id === 'new' &&
    (new URLSearchParams(location.search).has('legacy') ||
      new URLSearchParams(location.search).has('kind'))
  )
    content = <DeveloperOnly />;
  else if (section === 'reports')
    content =
      id === 'new' ? (
        <AggregateReportForm key={location.search} />
      ) : id ? (
        <Report key={id} id={id} />
      ) : (
        <Reports />
      );
  else if (section === 'schedules') content = <Schedules scheduleId={id} />;
  else if (section === 'jobs' && id) content = <JobRoute id={id} />;
  else if (section === 'operator-guide')
    content = (
      <>
        <PageHead
          eyebrow="GUIDE"
          title="결과를 읽는 방법"
          description="무엇을 확인했고, 무엇이 아직 남아 있는지 구분하세요."
        />
        <Panel title="사건 분석">
          <p className="live-padding">
            사건을 열면 최신 조사 상태와 마지막 공개 결과가 함께 표시됩니다. 분석 완료는 원인
            확정이나 복구 완료를 뜻하지 않습니다. 판단 제한과 다음 확인 사항을 읽고 실제 수행한
            조치는 별도로 기록하세요.
          </p>
        </Panel>
        <Panel title="운영 보고서">
          <p className="live-padding">
            분석 대상 기간과 범위를 먼저 확인하세요. 부분 산출과 판단 보류는 정상 수치가 아닙니다.
            보고서는 저장된 관측을 설명하며, 장비 조치는 담당자가 판단하고 수행합니다.
          </p>
        </Panel>
        <Link className="button" to="/reports">
          보고서 보기
        </Link>
      </>
    );
  else content = <DeveloperOnly />;
  const reportSection =
    section === 'reports' &&
    id === 'new' &&
    new URLSearchParams(location.search).get('schedule') === 'true'
      ? 'schedules'
      : section;
  return (
    <div
      className="page new-workspace"
      onClickCapture={(event) => {
        const anchor = (event.target as HTMLElement).closest('a');
        const hash = anchor?.getAttribute('href');
        if (
          !hash?.startsWith('#') ||
          event.button !== 0 ||
          event.ctrlKey ||
          event.metaKey ||
          event.shiftKey ||
          event.altKey
        )
          return;
        // Native fragment navigation discards React Router's return state.
        event.preventDefault();
        event.stopPropagation();
        navigate(
          { pathname: location.pathname, search: location.search, hash },
          { state: location.state },
        );
      }}
    >
      {['reports', 'schedules', 'operator-guide'].includes(section) &&
        !(app.mode === 'operations' && section === 'schedules') && (
          <nav className="tabs new-report-nav" aria-label="운영 보고서 메뉴">
            {[
              { to: '/reports', label: '보고서 목록', section: 'reports' },
              { to: '/schedules', label: '자동 보고서 설정', section: 'schedules' },
              { to: '/operator-guide', label: '보고서 읽는 방법', section: 'operator-guide' },
            ].map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={reportSection === item.section ? 'active' : ''}
                aria-current={reportSection === item.section ? 'location' : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      {content}
    </div>
  );
}
