import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, FileText, ScanSearch, Activity } from 'lucide-react';
import { useRecentIncidents } from '../components/IncidentOverview';
import { QueryState } from '../components/live';
import { RangeCalendar } from '../components/RangeCalendar';
import { Badge, NavTabs } from '../components/ui';
import { OpsUsage } from '../components/OpsUsage';
import { obj, queryPath, rows, str, useList, useResource } from '../lib/live';
import { useApp } from '../lib/store';
import {
  CATEGORIES,
  category,
  dailyCounts,
  dateTimeText,
  dayKey,
  fullDate,
  shortDate,
  titleText,
  windowDays,
  type IncidentView,
} from '../lib/incidentOverview';
import { reportTitle } from '../lib/workflow';
import { reportTabs } from '../lib/reportNavigation';
import { ReportPeriod } from '../components/ReportMeta';
import { OperatorConsole } from './ConsoleWorkspace';
import { NewWorkspace } from './NewWorkspace';
import './console2.css';

const qualityLabels: Record<string, string> = {
  ready: '산출 완료',
  partial: '부분 산출',
  blocked: '판단 보류',
  running: '조사 중',
  failed: '실행 실패',
  notice: '알림만',
  none: '공개 결과 미확인',
};
export const console2DeviceKey = (v: IncidentView) =>
  JSON.stringify([v.cluster, v.node, v.device, v.code]);
export function console2Date(value: string | null, today: string) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value > today) return '';
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? value : '';
}
export function console2Repeats(views: IncidentView[]) {
  const groups = new Map<string, IncidentView[]>();
  views.forEach((v) => {
    const key = console2DeviceKey(v);
    groups.set(key, [...(groups.get(key) || []), v]);
  });
  return [...groups.values()].filter((g) => g.length >= 3).sort((a, b) => b.length - a.length);
}
export function console2Filter(views: IncidentView[], params: URLSearchParams) {
  const search = (params.get('q') || '').trim().toLocaleLowerCase();
  const repeated = new Set(console2Repeats(views).map((g) => console2DeviceKey(g[0])));
  return views.filter(
    (v) =>
      (!search ||
        [titleText(v), v.node, v.cluster, v.device, v.raw]
          .join(' ')
          .toLocaleLowerCase()
          .includes(search)) &&
      (!params.get('node') || v.node === params.get('node')) &&
      (!params.get('cluster') || v.cluster === params.get('cluster')) &&
      (!params.get('quality') ||
        (params.get('quality') === 'limited'
          ? ['partial', 'blocked'].includes(v.rca)
          : v.rca === params.get('quality'))) &&
      (!params.get('device2') || console2DeviceKey(v) === params.get('device2')) &&
      (params.get('focus') !== 'firing' || v.firing) &&
      (params.get('focus') !== 'resolved' || v.resolved) &&
      (params.get('focus') !== 'repeat' || repeated.has(console2DeviceKey(v))),
  );
}
function Heading({ title, note, children }: { title: string; note: string; children?: ReactNode }) {
  return (
    <header className="c2-heading">
      <div>
        <span className="c2-eyebrow">GPU OPS / CONSOLE 02</span>
        <h1 tabIndex={-1}>{title}</h1>
        <p>{note}</p>
      </div>
      <div className="c2-actions">{children}</div>
    </header>
  );
}
function Surface({
  title,
  note,
  action,
  children,
}: {
  title: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="c2-surface">
      <header>
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
function IncidentTable({ views }: { views: IncidentView[] }) {
  const location = useLocation();
  const from = location.pathname + location.search;
  return (
    <div className="c2-table-scroll">
      <table className="c2-table">
        <caption className="sr-only">사건별 대상, 수신 상태와 공개 RCA 결과</caption>
        <thead>
          <tr>
            <th>사건 / 대상</th>
            <th>알림 수신</th>
            <th>RCA 결과</th>
            <th>발생 시각 · KST</th>
          </tr>
        </thead>
        <tbody>
          {views.map((v) => (
            <tr key={v.id} id={`c2-incident-${v.id}`}>
              <td>
                <Link
                  className="c2-title-link"
                  to={
                    v.jobId && ['ready', 'partial', 'blocked'].includes(v.rca)
                      ? `/analyses/${encodeURIComponent(v.jobId)}`
                      : `/incidents/${encodeURIComponent(v.id)}`
                  }
                  state={{ from, returnState: { row: v.id } }}
                >
                  {titleText(v)}
                  <ArrowUpRight size={14} />
                </Link>
                <small>
                  {v.cluster || '클러스터 미확인'} / {v.node || '노드 미확인'}
                  {v.device && (
                    <>
                      {' '}
                      · <code>{v.device}</code>
                    </>
                  )}
                </small>
              </td>
              <td>
                <span className={`c2-status ${v.firing ? 'attention' : 'neutral'}`}>
                  {v.firing ? '발생 수신' : v.resolved ? '해제 수신' : '미확인'}
                </span>
              </td>
              <td>
                <span
                  className={`c2-status ${['partial', 'blocked', 'failed'].includes(v.rca) ? 'warning' : 'neutral'}`}
                >
                  {qualityLabels[v.rca]}
                </span>
              </td>
              <td>
                <time>{dateTimeText(v.at)}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function PeriodButtons({
  period,
  onChange,
  includeAll = false,
}: {
  period: string;
  onChange: (value: string) => void;
  includeAll?: boolean;
}) {
  return (
    <div className="c2-segment" aria-label="사건 조회 기간">
      {[
        ['1', '오늘'],
        ['7', '7일'],
        ['14', '14일'],
        ['30', '30일'],
        ...(includeAll ? [['all', '전체']] : []),
      ].map(([value, label]) => (
        <button key={value} aria-pressed={period === value} onClick={() => onChange(value)}>
          {label}
        </button>
      ))}
    </div>
  );
}
function Overview() {
  const app = useApp();
  const [params, setParams] = useSearchParams();
  const period = ['1', '7', '14', '30'].includes(params.get('period') || '')
    ? params.get('period')!
    : '14';
  const { query, views, now, truncated } = useRecentIncidents(
    windowDays(new Date(), Number(period))[0],
  );
  const modules = useResource('/service-status');
  const reports = useList(
    app.ready ? queryPath('/reports', { scope: app.scope, status: 'succeeded', limit: 3 }) : null,
  );
  const publishedReports = reports.items.filter((j) => !!j.result_ref && !j.deletion);
  const days = windowDays(now, Number(period));
  const daily = dailyCounts(views, days);
  const max = Math.max(1, ...daily.map((d) => Object.values(d.counts).reduce((a, b) => a + b, 0)));
  const repeats = console2Repeats(views);
  const nodes = [...new Set(views.map((v) => JSON.stringify([v.cluster, v.node])))];
  const partial = views.filter((v) => v.rca === 'partial' || v.rca === 'blocked');
  const scopeNote = query.hasNextPage
    ? '불러온 사건 기준 · 추가 자료 확인 중 또는 조회 한도 도달'
    : '선택 범위의 저장 사건 기준';
  return (
    <div className="c2-page">
      <Heading title="운영 개요" note={`최근 ${period}일 · ${dateTimeText(now)} 기준`}>
        <PeriodButtons period={period} onChange={(v) => setParams({ period: v })} />
        <Link className="button primary" to="/reports/new">
          <FileText size={16} /> 보고서 만들기
        </Link>
      </Heading>
      <QueryState query={query}>
        <div className="c2-context">
          <Activity size={15} />
          <span>{scopeNote}. 알림 수신 기록은 현재 장애·복구 상태가 아닙니다.</span>
        </div>
        {truncated && (
          <p role="status" className="c2-warning">
            최근 1,000건까지만 조회했습니다. 기간을 좁혀 전체 자료를 확인하세요.
          </p>
        )}
        <div className="c2-kpis">
          {[
            ['수신된 사건', views.length, '조회 기간에 기록된 사건', `/cases?period=${period}`],
            [
              '발생 알림 수신',
              views.filter((v) => v.firing).length,
              '현재 상태는 별도 확인',
              `/cases?period=${period}&focus=firing`,
            ],
            [
              '3회 이상 반복',
              repeats.length,
              '같은 클러스터·장치·오류 묶음',
              `/cases?period=${period}&focus=repeat`,
            ],
            [
              '추가 자료 확인',
              partial.length,
              '부분 산출·판단 보류 결과',
              `/cases?period=${period}&quality=limited`,
            ],
          ].map(([label, value, note, to]) => (
            <Link className="c2-kpi" key={label} to={String(to)}>
              <span>
                {label}
                <ArrowUpRight size={15} />
              </span>
              <strong>{value}</strong>
              <small>{note}</small>
            </Link>
          ))}
        </div>
        <div className="c2-overview-grid">
          <Surface
            title="최근 수신된 사건"
            note="최신 6건 · 발생 시각 순"
            action={<Link to={`/cases?period=${period}`}>사건 전체 보기 →</Link>}
          >
            {views.length ? (
              <IncidentTable views={views.slice(0, 6)} />
            ) : (
              <p className="c2-empty">
                조회 기간의 사건이 없습니다. 다른 기간이나 범위를 선택하세요.
              </p>
            )}
          </Surface>
          <Surface title="반복 발생 대상" note="동일 장치·동일 오류 3회 이상">
            {repeats.slice(0, 5).map((group) => (
              <Link
                key={console2DeviceKey(group[0])}
                className="c2-repeat"
                to={`/cases?period=${period}&device2=${encodeURIComponent(console2DeviceKey(group[0]))}`}
              >
                <div>
                  <b>{group[0].node || '노드 미확인'}</b>
                  <small>
                    {group[0].cluster} · {group[0].codeText || titleText(group[0])}
                  </small>
                  <code>{group[0].device || '장치 식별 미확인'}</code>
                </div>
                <strong>
                  {group.length}
                  <small>회</small>
                </strong>
              </Link>
            ))}
            {!repeats.length && (
              <p className="c2-empty">같은 대상·오류가 3회 이상 반복된 기록이 없습니다.</p>
            )}
            <Link className="c2-foot-link" to={`/cases?period=${period}&focus=repeat`}>
              반복 사건 확인 →
            </Link>
          </Surface>
        </div>
        <div className="c2-overview-grid">
          <Surface title="사건 수신 추이" note="날짜를 선택하면 해당 날짜의 사건으로 이동">
            <div
              className="c2-trend"
              style={{ gridTemplateColumns: `repeat(${days.length},minmax(20px,1fr))` }}
            >
              {daily.map((d) => {
                const count = Object.values(d.counts).reduce((a, b) => a + b, 0);
                return (
                  <Link
                    key={d.day}
                    to={`/cases?from=${d.day}&to=${d.day}`}
                    aria-label={`${fullDate(d.day)} 사건 ${count}건`}
                  >
                    <span>{count}</span>
                    <i style={{ height: `${Math.max(2, (count / max) * 120)}px` }} />
                    <small>{shortDate(d.day).slice(0, 5)}</small>
                  </Link>
                );
              })}
            </div>
          </Surface>
          <Surface title="유형별 수신 기록" note="오류 유형은 장비의 현재 상태와 다릅니다.">
            <div className="c2-categories">
              {CATEGORIES.map((c) => {
                const n = views.filter((v) => category(v) === c.key).length;
                return (
                  <div key={c.key}>
                    <span>{c.name}</span>
                    <b>{n}건</b>
                    <i style={{ width: `${views.length ? (n / views.length) * 100 : 0}%` }} />
                  </div>
                );
              })}
            </div>
          </Surface>
        </div>
        <Surface
          title="노드별 사건 분포"
          note="클러스터·노드별로 구분합니다. 노드를 선택하면 사건을 좁혀 봅니다."
        >
          <div className="c2-node-grid">
            {nodes.map((key) => {
              const [cluster, node] = JSON.parse(key) as string[];
              const group = views.filter((v) => v.cluster === cluster && v.node === node);
              return (
                <Link
                  key={key}
                  to={`/cases?period=${period}&cluster=${encodeURIComponent(cluster)}&node=${encodeURIComponent(node)}`}
                >
                  <span>{cluster || '클러스터 미확인'}</span>
                  <b>{node || '노드 미확인'}</b>
                  <strong>
                    {group.length}
                    <small>건</small>
                  </strong>
                </Link>
              );
            })}
          </div>
        </Surface>
      </QueryState>
      <Surface
        title="최근 발행된 Ops 보고서"
        note="저장된 분석 기간의 결과 · 현재 관측과 구분"
        action={<Link to="/reports">보고서 전체 보기 →</Link>}
      >
        <QueryState
          query={reports}
          empty={!publishedReports.length}
          emptyTitle="최근 조회한 요청에 발행된 보고서가 없습니다."
        >
          <div className="c2-report-teasers">
            {publishedReports.map((j) => (
              <Link
                key={str(j.id)}
                to={`/reports/${str(j.id)}`}
                state={{ from: '/dashboard' + (params.size ? '?' + params.toString() : '') }}
              >
                <FileText size={20} />
                <b>{reportTitle(j)}</b>
                <ReportPeriod value={j.time_range} />
                <Badge status={str(j.result_status) || null} />
              </Link>
            ))}
          </div>
        </QueryState>
      </Surface>
      <details className="c2-usage">
        <summary>최근 Ops 보고서의 GPU 사용 현황 보기</summary>
        <OpsUsage />
      </details>
      <footer className="c2-service">
        <span>조회 서비스</span>
        {['incident', 'job_controller'].map((name) => {
          const status = str(rows(modules.data?.items).find((m) => m.module === name)?.status);
          return (
            <span key={name}>
              {name === 'incident' ? '사건 수신' : 'RCA 실행'} ·{' '}
              {status === 'available'
                ? '응답 정상'
                : status === 'unavailable'
                  ? '응답 확인 실패'
                  : '미확인'}
            </span>
          );
        })}
        <Link to="/settings/backend">연결 상태 →</Link>
      </footer>
    </div>
  );
}
function Cases() {
  const [params, setParams] = useSearchParams();
  const period = ['1', '7', '14', '30'].includes(params.get('period') || '')
    ? params.get('period')!
    : 'all';
  const today = dayKey(new Date());
  const picked = console2Date(params.get('from'), today);
  const first = picked || (period === 'all' ? null : windowDays(new Date(), Number(period))[0]);
  const end = console2Date(params.get('to'), today);
  const last = picked ? (end >= picked ? end : picked) : today;
  const { query, views, truncated } = useRecentIncidents(first, last);
  const filtered = console2Filter(views, params);
  const [search, setSearch] = useState(params.get('q') || '');
  const update = (values: Record<string, string>) => {
    const next = new URLSearchParams(params);
    if (!('page' in values)) next.delete('page');
    Object.entries(values).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key),
    );
    setParams(next);
  };
  useEffect(() => setSearch(params.get('q') || ''), [params]);
  const page = Math.max(
    1,
    Math.min(Math.ceil(filtered.length / 25) || 1, Math.floor(Number(params.get('page'))) || 1),
  );
  const location = useLocation();
  useEffect(() => {
    const row = str(obj(location.state).row);
    if (row)
      requestAnimationFrame(() => {
        const link = document.querySelector<HTMLAnchorElement>(
          `[id="c2-incident-${CSS.escape(row)}"] a`,
        );
        link?.focus({ preventScroll: true });
        link?.scrollIntoView({ block: 'center' });
      });
  }, [location.state, query.isPending]);
  return (
    <div className="c2-page">
      <Heading title="RCA 조사" note="사건을 찾고, 저장된 분석과 다음 확인을 읽습니다." />
      <section className="c2-surface">
        <form
          className="c2-search"
          onSubmit={(e) => {
            e.preventDefault();
            update({ q: search.trim() });
          }}
        >
          <ScanSearch size={19} />
          <input
            aria-label="사건 검색"
            placeholder="노드, 오류 코드, PCI 또는 알림 내용 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="button primary">검색</button>
        </form>
        <div className="c2-filters">
          <label>
            클러스터
            <select
              value={params.get('cluster') || ''}
              onChange={(e) => update({ cluster: e.target.value, node: '' })}
            >
              <option value="">전체</option>
              {[...new Set(views.map((v) => v.cluster).filter(Boolean))].sort().map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label>
            노드
            <select
              value={params.get('node') || ''}
              onChange={(e) => update({ node: e.target.value })}
            >
              <option value="">전체</option>
              {[
                ...new Set(
                  views
                    .filter((v) => !params.get('cluster') || v.cluster === params.get('cluster'))
                    .map((v) => v.node)
                    .filter(Boolean),
                ),
              ]
                .sort()
                .map((n) => (
                  <option key={n}>{n}</option>
                ))}
            </select>
          </label>
          <label>
            알림 수신
            <select
              value={params.get('focus') || ''}
              onChange={(e) => update({ focus: e.target.value })}
            >
              <option value="">전체</option>
              <option value="firing">발생 수신</option>
              <option value="resolved">해제 수신</option>
              <option value="repeat">3회 이상 반복</option>
            </select>
          </label>
          <label>
            RCA 결과
            <select
              value={params.get('quality') || ''}
              onChange={(e) => update({ quality: e.target.value })}
            >
              <option value="">전체</option>
              <option value="limited">부분 산출·판단 보류</option>
              {Object.entries(qualityLabels).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="c2-filter-period">
          <PeriodButtons
            includeAll
            period={picked ? '' : period}
            onChange={(p) => update({ period: p, from: '', to: '' })}
          />
          <RangeCalendar
            first={first || (views.length ? dayKey(views[views.length - 1].at) : today)}
            last={last}
            today={dayKey(new Date())}
            label={picked ? `${first} ~ ${last}` : '날짜 선택'}
            onChange={(from, to) => update({ from, to, period: '' })}
          />
          <button className="text-link" onClick={() => setParams({})}>
            조건 초기화
          </button>
        </div>
      </section>
      {!query.isPending && !query.isError && (
        <div className="c2-list-note">
          <b>{filtered.length}건</b>
          <span>불러온 {views.length}건에서 검색 · 수신 기록은 현재 장애 상태가 아닙니다.</span>
          {params.get('device2') && (
            <button className="button" onClick={() => update({ device2: '' })}>
              동일 장치·오류 조건 해제
            </button>
          )}
        </div>
      )}
      {truncated && (
        <p role="status" className="c2-warning">
          최근 1,000건까지만 불러왔습니다. 기간을 좁혀 검색하세요.
        </p>
      )}
      <QueryState
        query={query}
        empty={!filtered.length}
        emptyTitle="조건에 맞는 사건이 없습니다."
        emptyDescription="검색어·기간·클러스터 조건을 확인하거나 조건을 초기화하세요."
      >
        <div className="c2-surface">
          <IncidentTable views={filtered.slice((page - 1) * 25, page * 25)} />
        </div>
        <nav className="c2-pagination" aria-label="사건 페이지">
          <button
            className="button"
            disabled={page === 1}
            onClick={() => update({ page: String(page - 1) })}
          >
            이전
          </button>
          <span>
            {page} / {Math.max(1, Math.ceil(filtered.length / 25))}
          </span>
          <button
            className="button"
            disabled={page * 25 >= filtered.length}
            onClick={() => update({ page: String(page + 1) })}
          >
            다음
          </button>
        </nav>
      </QueryState>
    </div>
  );
}
const reportSections = [
  ['c2-report-summary', '핵심 요약'],
  ['c2-rca-decision', '사건 판단'],
  ['rca-response-reference', '대응 순서'],
  ['rca-observation-detail', '로그·지표'],
  ['rca-analysis-detail', '분석·근거'],
  ['c2-rca-history', '발생 이력'],
  ['c2-rca-references', '참고 자료'],
  ['namespace-summary-title', 'Namespace 활동'],
  ['c2-namespace-charts', '시간대 그래프'],
  ['c2-workloads', '작업 대기·완료'],
  ['incident-summary-title', '장애 알림'],
  ['report-evidence', '집계 근거'],
  ['new-review-records', '검토·조치 기록'],
];
function Reader({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [sections, setSections] = useState<string[][]>([]),
    [active, setActive] = useState('');
  const location = useLocation();
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    let frame = 0;
    const scan = () => {
      const found = reportSections.filter(([id]) => element.querySelector(`[id="${id}"]`));
      setSections((previous) =>
        JSON.stringify(previous) === JSON.stringify(found) ? previous : found,
      );
      setActive((previous) =>
        found.some(([id]) => id === previous) ? previous : found[0]?.[0] || '',
      );
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(element, { childList: true, subtree: true });
    const position = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const found = reportSections.filter(([id]) => element.querySelector(`[id="${id}"]`));
        setActive(
          found
            .filter(
              ([id]) =>
                !!document.getElementById(id)?.getClientRects().length &&
                (document.getElementById(id)?.getBoundingClientRect().top ?? Infinity) < 180,
            )
            .at(-1)?.[0] ||
            found[0]?.[0] ||
            '',
        );
      });
    };
    window.addEventListener('scroll', position, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', position);
      cancelAnimationFrame(frame);
    };
  }, [location.pathname, location.search]);
  const jump = (id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    for (let p = target.parentElement; p; p = p.parentElement)
      if (p instanceof HTMLDetailsElement) p.open = true;
    if (target instanceof HTMLDetailsElement) target.open = true;
    target.tabIndex = -1;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: 'start' });
  };
  return (
    <div className="c2-reader-layout">
      <aside className="c2-toc">
        <span>IN THIS REPORT</span>
        <b>보고서 목차</b>
        <select aria-label="보고서 구역 이동" value={active} onChange={(e) => jump(e.target.value)}>
          {sections.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
        <nav aria-label="고정 보고서 목차">
          {sections.map(([id, label]) => (
            <button
              key={id}
              aria-current={active === id ? 'location' : undefined}
              onClick={() => jump(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <p>
          저장된 관측과
          <br />
          판단 한계를 함께 읽으세요.
        </p>
        <button
          className="text-link"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        >
          보고서 처음으로 ↑
        </button>
      </aside>
      <div ref={root} className="c2-reader-content">
        {children}
      </div>
    </div>
  );
}
export function Console2() {
  const location = useLocation();
  if (location.pathname === '/dashboard') return <Overview />;
  if (location.pathname === '/cases') return <Cases />;
  if (location.pathname === '/reports')
    return (
      <div className="c2-page c2-report-list">
        <NavTabs items={reportTabs} />
        <OperatorConsole compact />
      </div>
    );
  if (
    /^\/(analyses|incidents)\/[^/]+$/.test(location.pathname) ||
    /^\/reports\/(?!new$)[^/]+$/.test(location.pathname)
  )
    return (
      <Reader key={location.pathname}>
        <NewWorkspace />
      </Reader>
    );
  if (
    /^\/(reports|schedules)(\/|$)/.test(location.pathname) ||
    location.pathname === '/operator-guide'
  )
    return (
      <div className="c2-secondary">
        <NewWorkspace />
      </div>
    );
  return (
    <div className="c2-secondary">
      <Outlet />
    </div>
  );
}
