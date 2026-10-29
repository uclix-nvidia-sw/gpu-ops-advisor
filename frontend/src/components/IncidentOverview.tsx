import { useEffect, useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { queryPath, useList } from '../lib/live';
import { useApp } from '../lib/store';
import {
  ago,
  clock,
  dateTimeText,
  dayKey,
  fullDate,
  incidentViews,
  kindText,
  titleText,
  windowDays,
  type IncidentView,
} from '../lib/incidentOverview';
import './operator-home.css';

export const WINDOW_DAYS = 14;
// The Backend accepts at most 200 per page; later pages load automatically.
const LIMIT = 200;
const MAX_PAGES = 5;

/**
 * Incidents in the selected scope, refreshed every minute: by default the last two weeks;
 * `first`/`last` are inclusive KST days, and `first: null` means from the beginning.
 */
export function useRecentIncidents(first?: string | null, last?: string) {
  const app = useApp();
  // timeRange changes on the header refresh, which also moves the window forward.
  const now = useMemo(() => new Date(), [app.timeRange]);
  // From KST midnight of the first day, so every count covers whole days.
  const start = first === undefined ? windowDays(now, WINDOW_DAYS)[0] : first;
  const midnight = (day: string, offset = 0) =>
    new Date(Date.parse(`${day}T00:00:00+09:00`) + offset).toISOString();
  const query = useList(
    app.ready
      ? queryPath('/incidents', {
          scope: app.scope,
          from: start ? midnight(start) : undefined,
          to: last ? midnight(last, 86_400_000) : undefined,
          limit: LIMIT,
        })
      : null,
  );
  const { refetch, hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  const pages = query.data?.pages.length || 0;
  useEffect(() => {
    const timer = window.setInterval(() => void refetch(), 60_000);
    return () => window.clearInterval(timer);
  }, [refetch]);
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && pages < MAX_PAGES) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, pages, fetchNextPage]);
  const views = useMemo(() => incidentViews(query.items), [query.items]);
  return { query, views, now, truncated: hasNextPage === true && pages >= MAX_PAGES };
}

export function DeviceText({ v }: { v: Pick<IncidentView, 'node' | 'kind' | 'device'> }) {
  return (
    <>
      {v.node || '노드 미확인'} · {kindText(v.kind)}
      {v.device && <code className="oh-code">{v.device}</code>}
    </>
  );
}

/** Soft badge for an XID/SXID code; components have none. */
export function CodeBadge({ code, text }: { code: string; text: string }) {
  if (!text) return null;
  return <span className={`oh-badge ${code.startsWith('sxid:') ? 'sx' : ''}`}>{text}</span>;
}

export function RepeatBadge({ v }: { v: IncidentView }) {
  if (v.kind === 'host') return null;
  return (
    <span className={`oh-rep ${v.nth >= 3 ? 'hot' : ''}`} title="조회한 기간 중">
      이 {v.kind === 'switch' ? '스위치' : 'GPU'} {v.nth}번째
    </span>
  );
}

/** Colour lives in the dot only; the words stay in the body colour. */
export function AlarmState({ v, now }: { v: IncidentView; now: Date }) {
  if (v.firing)
    return (
      <div className="oh-st">
        <b>
          <i className="oh-dot red" />
          발생 알림 수신
        </b>
        <small>{ago(v.at, now)} 전 시작</small>
      </div>
    );
  if (!v.resolved) return <div className="oh-st">알림 상태 미확인</div>;
  return (
    <div className="oh-st resolved">
      <b>
        <i className="oh-dot" />
        해제 알림 수신
      </b>
      <small>{v.resolvedAt ? dateTimeText(v.resolvedAt) : '해제 시각 미확인'}</small>
    </div>
  );
}

/** The published RCA report of an incident, if any. */
export const reportPath = (v: IncidentView) =>
  ['ready', 'partial', 'blocked'].includes(v.rca) && v.jobId
    ? `/analyses/${v.jobId}#final-report`
    : '';

/** The report when one exists; no result-quality labels on the list. */
export function RcaLink({ v, button = false }: { v: IncidentView; button?: boolean }) {
  const report = reportPath(v);
  const running = ['running', 'failed'].includes(v.rca) && v.jobId;
  // "목록으로" on the report returns to this list with its dates and page.
  const location = useLocation();
  const state = { from: location.pathname + location.search };
  if (report)
    return (
      <Link className={button ? 'oh-btn' : 'oh-rca'} to={report} state={state}>
        {button ? 'RCA 보고서 열기' : '보고서 열기'}
      </Link>
    );
  if (button) return null;
  if (running)
    return (
      <Link className="oh-rca quiet" to={`/jobs/${v.jobId}`} state={state}>
        {v.rca === 'running' ? 'RCA 실행 중' : '실행 이력'}
      </Link>
    );
  return <span className="oh-rca none">{v.rca === 'notice' ? '알림만' : '—'}</span>;
}

/** Code badge and the Korean name; list rows link it to the RCA report. */
export function ErrorTitle({ v }: { v: IncidentView }) {
  return (
    <>
      <CodeBadge code={v.code} text={v.codeText} />
      <b className="oh-name">{titleText({ ...v, codeText: '' })}</b>
    </>
  );
}

export function IncidentRow({
  v,
  now,
  showDate = false,
}: {
  v: IncidentView;
  now: Date;
  showDate?: boolean;
}) {
  const location = useLocation();
  return (
    <div className={`oh-row ${v.firing ? 'firing' : ''}`}>
      <div className="oh-t">
        {clock(v.at)}
        {showDate && <small>{fullDate(dayKey(v.at)).slice(5)}</small>}
      </div>
      <div className="oh-what">
        {reportPath(v) ? (
          <Link
            className="oh-title"
            to={reportPath(v)}
            state={{ from: location.pathname + location.search }}
          >
            <ErrorTitle v={v} />
          </Link>
        ) : (
          <ErrorTitle v={v} />
        )}
        {(v.reason || (v.label?.detail && !/Unused|미사용/i.test(v.label.detail))) && (
          <span className="oh-detail">{v.reason || v.label?.detail}</span>
        )}
        <small title={v.raw}>원문: {v.raw}</small>
      </div>
      <div className="oh-where">
        <DeviceText v={v} />
        <small>
          <RepeatBadge v={v} />
        </small>
      </div>
      <AlarmState v={v} now={now} />
      <div className="oh-act">{v.label?.action || '런북 순서대로 확인'}</div>
      <RcaLink v={v} />
    </div>
  );
}

export function IncidentHead() {
  return (
    <div className="oh-lh" aria-hidden="true">
      <span>시각</span>
      <span>무슨 장애</span>
      <span>어디</span>
      <span>수신된 알림 상태</span>
      <span>NVIDIA 즉시 조치 분류</span>
      <span>RCA</span>
    </div>
  );
}
