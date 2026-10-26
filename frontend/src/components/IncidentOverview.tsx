import { useEffect, useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { queryPath, useList } from '../lib/live';
import { useApp } from '../lib/store';
import {
  ago,
  incidentViews,
  kindText,
  titleText,
  type DeviceRepeat,
  type IncidentView,
} from '../lib/incidentOverview';
import './operator-home.css';

export const WINDOW_DAYS = 14;
// The Backend accepts at most 200 per page; later pages load automatically.
const LIMIT = 200;
const MAX_PAGES = 5;

/** Incidents of the last two weeks in the selected scope, refreshed every minute. */
export function useRecentIncidents() {
  const app = useApp();
  // timeRange changes on the header refresh, which also moves the window forward.
  const now = useMemo(() => new Date(), [app.timeRange]);
  const from = new Date(now.getTime() - WINDOW_DAYS * 24 * 3600_000);
  from.setSeconds(0, 0);
  const query = useList(
    app.ready
      ? queryPath('/incidents', { scope: app.scope, from: from.toISOString(), limit: LIMIT })
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
  const views = useMemo(() => incidentViews(query.items, now), [query.items, now]);
  return { query, views, now, truncated: hasNextPage === true && pages >= MAX_PAGES };
}

const time = (d: Date) =>
  d.toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
export const dateTime = (d: Date) =>
  d.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

export function DeviceText({ v }: { v: Pick<IncidentView, 'node' | 'kind' | 'device'> }) {
  return (
    <>
      {v.node || '노드 미확인'} · {kindText(v.kind)}
      {v.device && <code className="oh-code">{v.device}</code>}
    </>
  );
}

export function RepeatBadge({ v }: { v: IncidentView }) {
  if (v.kind === 'host') return null;
  return (
    <span className={`oh-rep ${v.nth >= 3 ? 'hot' : ''}`} title={`최근 ${WINDOW_DAYS}일 중`}>
      이 {v.kind === 'switch' ? '스위치' : 'GPU'} {v.nth}번째
    </span>
  );
}

export function AlarmState({ v, now }: { v: IncidentView; now: Date }) {
  if (v.stale)
    return (
      <div className="oh-st stale">
        <span className="dot" />
        확인 필요
        <small>{ago(v.at, now)}째 '발생 중' · 해제 신호 없음</small>
      </div>
    );
  if (v.firing)
    return (
      <div className="oh-st firing">
        <span className="dot" />
        발생 중<small>{ago(v.at, now)} 전 시작</small>
      </div>
    );
  return (
    <div className="oh-st">
      <span className="dot" />
      해제됨<small>{v.resolvedAt ? dateTime(v.resolvedAt) : '해제 시각 미확인'}</small>
    </div>
  );
}

/** The report when one exists; no result-quality labels on the list. */
export function RcaLink({ v, button = false }: { v: IncidentView; button?: boolean }) {
  const report = ['ready', 'partial', 'blocked'].includes(v.rca) && v.jobId;
  const running = ['running', 'failed'].includes(v.rca) && v.jobId;
  if (report)
    return (
      <Link
        className={button ? 'button primary' : 'oh-rca'}
        to={`/analyses/${v.jobId}#final-report`}
      >
        {button ? 'RCA 보고서 열기' : '보고서 열기'}
      </Link>
    );
  if (button) return null;
  if (running)
    return (
      <Link className="oh-rca quiet" to={`/jobs/${v.jobId}`}>
        {v.rca === 'running' ? 'RCA 실행 중' : '실행 이력'}
      </Link>
    );
  return <span className="oh-rca none">{v.rca === 'notice' ? '알림만' : '—'}</span>;
}

/** Code badge and the Korean name; components have no code. */
export function ErrorTitle({ v }: { v: IncidentView }) {
  const name = titleText({ ...v, codeText: '' });
  return (
    <>
      {v.codeText && <span className="oh-badge">{v.codeText}</span>}
      <b>{name}</b>
    </>
  );
}

export function IncidentRow({ v, now }: { v: IncidentView; now: Date }) {
  const location = useLocation();
  return (
    <div className={`oh-row ${v.stale ? 'stale' : v.firing ? 'firing' : ''}`}>
      <div className="oh-t">
        {time(v.at)}
        <small>{dateTime(v.at).slice(0, 6)}</small>
      </div>
      <div className="oh-what">
        <Link to={`/incidents/${v.id}`} state={{ from: location.pathname + location.search }}>
          <ErrorTitle v={v} />
        </Link>
        {(v.reason || v.label?.detail) && (
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
    <div className="oh-head" aria-hidden="true">
      <span>발생</span>
      <span>무슨 장애</span>
      <span>어디</span>
      <span>알림</span>
      <span>NVIDIA 즉시 조치 분류</span>
      <span>RCA</span>
    </div>
  );
}

export function DeviceTable({
  items,
  onSelect,
}: {
  items: DeviceRepeat[];
  onSelect?: (key: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="oh-table">
        <thead>
          <tr>
            <th scope="col">노드 · 장치</th>
            <th scope="col">오류</th>
            <th scope="col">{WINDOW_DAYS}일 발생</th>
            <th scope="col">날짜별</th>
            <th scope="col">마지막</th>
            {onSelect && <th scope="col" />}
          </tr>
        </thead>
        <tbody>
          {items.map((d) => {
            const max = Math.max(...d.perDay, 1);
            return (
              <tr key={d.key}>
                <td>
                  <b>{d.node}</b> · {kindText(d.kind)} <code className="oh-code">{d.device}</code>
                </td>
                <td>
                  <span className="oh-badge">{d.codeText}</span>
                  {d.name}
                </td>
                <td className="n">
                  <b className={d.count >= 3 ? 'oh-hot' : ''}>{d.count}회</b>
                </td>
                <td>
                  <div
                    className={`oh-spark ${d.kind}`}
                    aria-label={`날짜별 ${d.perDay.join(', ')}회`}
                  >
                    {d.perDay.map((n, i) => (
                      <i
                        key={i}
                        className={n ? '' : 'z'}
                        style={{ height: `${(n / max) * 22}px` }}
                      />
                    ))}
                  </div>
                </td>
                <td>{dateTime(d.last)}</td>
                {onSelect && (
                  <td>
                    <button className="text-link oh-link" onClick={() => onSelect(d.key)}>
                      사건 보기
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
