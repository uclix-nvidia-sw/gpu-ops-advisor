import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, FileText, ScanSearch, Activity } from 'lucide-react';
import { useRecentIncidents } from '../components/IncidentOverview';
import { QueryState } from '../components/live';
import { RangeCalendar } from '../components/RangeCalendar';
import { Badge, NavTabs } from '../components/ui';
import { OpsUsage } from '../components/OpsUsage';
import { IncidentCharts } from '../components/Console2Charts';
import { obj, queryPath, rows, str, useList, useResource } from '../lib/live';
import { useApp } from '../lib/store';
import {
  CATEGORIES,
  category,
  kindText,
  dateTimeText,
  dayKey,
  titleText,
  windowDays,
  type IncidentView,
} from '../lib/incidentOverview';
import { labels } from '../lib/domain';
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

  none: '공개 결과 미확인',
};
const executionStates = [
  'queued',
  'running',
  'retry_wait',
  'succeeded',
  'failed',
  'cancelled',
  'expired',
];
const publishedQuality = (v: IncidentView) =>
  v.publishedStatus || (['ready', 'partial', 'blocked'].includes(v.rca) ? v.rca : 'none');
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
  const filtered = views.filter(
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
          ? ['partial', 'blocked'].includes(publishedQuality(v))
          : publishedQuality(v) === params.get('quality'))) &&
      (!params.get('device2') || console2DeviceKey(v) === params.get('device2')) &&
      (!params.get('execution') || (v.executionStatus || 'none') === params.get('execution')) &&
      (!params.get('kind') || v.kind === params.get('kind')) &&
      (!params.get('code') || v.code === params.get('code')) &&
      (!params.get('category') || category(v) === params.get('category')) &&
      (params.get('focus') !== 'repeat' || repeated.has(console2DeviceKey(v))),
  );
  return filtered.sort((a, b) => {
    const sort = params.get('sort');
    if (sort === 'oldest') return a.at.getTime() - b.at.getTime();
    const group =
      sort === 'device'
        ? JSON.stringify([a.cluster, a.node, a.device]).localeCompare(
            JSON.stringify([b.cluster, b.node, b.device]),
          )
        : sort === 'error'
          ? a.code.localeCompare(b.code, undefined, { numeric: true })
          : 0;
    return group || b.at.getTime() - a.at.getTime();
  });
}
function Heading({ title, note, children }: { title: string; note: string; children?: ReactNode }) {
  return (
    <header className="c2-heading">
      <div>
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
export function IncidentTable({ views }: { views: IncidentView[] }) {
  const location = useLocation();
  const from = location.pathname + location.search;
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <div className="c2-table-scroll">
      <table className="c2-table c2-case-table">
        <caption className="sr-only">수신 alert의 사건·대상과 별도의 실행 상태·공개 결과</caption>
        <thead>
          <tr>
            <th>사건</th>
            <th>대상 장비</th>
            <th>런북 참고</th>
            <th>보고서</th>
            <th>발생 시각 · KST</th>
          </tr>
        </thead>
        <tbody>
          {views.map((v) => {
            const back = { from, returnState: { row: v.id } };
            const reportId =
              v.publishedJobId || (['ready', 'partial', 'blocked'].includes(v.rca) ? v.jobId : '');
            const open = expanded === v.id;
            return (
              <Fragment key={v.id}>
                <tr id={`c2-incident-${v.id}`} className={open ? 'c2-row-open' : ''}>
                  <td>
                    <Link
                      className="c2-title-link"
                      to={
                        reportId
                          ? `/analyses/${encodeURIComponent(reportId)}`
                          : `/incidents/${encodeURIComponent(v.id)}`
                      }
                      state={back}
                    >
                      <span>{titleText(v)}</span>
                      <ArrowUpRight size={14} />
                    </Link>
                  </td>
                  <td className="c2-device-cell">
                    <b>
                      {kindText(v.kind)} · {v.node || '노드 미확인'}
                    </b>
                    <small>{v.cluster || '클러스터 미확인'}</small>
                    <code>
                      {v.device
                        ? `${v.device.startsWith('GPU-') ? 'UUID' : 'PCI'} ${v.device}`
                        : '장치 식별 정보 없음'}
                    </code>
                  </td>
                  <td>
                    <span className="c2-guidance">
                      {v.label?.action.replace(/\s*\([A-Z_]+\)/g, '') || '등록된 안내 없음'}
                    </span>
                    <button
                      className="c2-expand"
                      aria-expanded={open}
                      aria-controls={`c2-detail-${v.id}`}
                      onClick={() => setExpanded(open ? null : v.id)}
                    >
                      {open ? '접기' : '원문·런북 안내'} {open ? '−' : '+'}
                    </button>
                  </td>
                  <td>
                    <Link
                      className="c2-execution-link"
                      to={`/incidents/${encodeURIComponent(v.id)}`}
                      state={back}
                    >
                      <span
                        className={`c2-status ${['queued', 'running', 'retry_wait'].includes(v.executionStatus || '') ? 'attention' : ['failed', 'cancelled', 'expired'].includes(v.executionStatus || '') ? 'warning' : 'neutral'}`}
                      >
                        {labels[v.executionStatus || ''] || v.executionStatus || '실행 기록 없음'}
                      </span>
                    </Link>
                    <span
                      className={`c2-result-quality ${['partial', 'blocked'].includes(publishedQuality(v)) ? 'warning' : ''}`}
                    >
                      {qualityLabels[publishedQuality(v)] || publishedQuality(v)}
                    </span>
                    {reportId && (
                      <Link
                        className="c2-result-link"
                        to={`/analyses/${encodeURIComponent(reportId)}`}
                        state={back}
                      >
                        {v.latestJobId && v.latestJobId !== reportId
                          ? '이전 발행 보고서'
                          : '보고서 열기'}{' '}
                        →
                      </Link>
                    )}
                  </td>
                  <td>
                    <time dateTime={v.at.toISOString()}>{dateTimeText(v.at)}</time>
                  </td>
                </tr>
                <tr id={`c2-detail-${v.id}`} hidden={!open} className="c2-detail-row">
                  <td colSpan={5}>
                    {open && (
                      <div className="c2-case-detail">
                        <section>
                          <h3>수신 alert 원문</h3>
                          <p className="c2-alert-raw">{v.raw || '수신 내용 없음'}</p>
                          <dl>
                            <dt>컴포넌트</dt>
                            <dd>{v.component || '미확인'}</dd>
                            <dt>GPU UUID</dt>
                            <dd>{v.uuid || '수신 정보 없음'}</dd>
                          </dl>
                        </section>
                        <section>
                          <h3>런북 코드별 참고 안내</h3>
                          <p>
                            일반 지침이며 이 사건의 RCA 결론이나 수행 완료 기록이 아닙니다. 실제
                            적용 조건과 절차는 보고서에서 확인하세요.
                          </p>
                          {v.label ? (
                            <>
                              <b>{v.label.action}</b>
                              <p>{v.label.steps.join(' → ')}</p>
                            </>
                          ) : (
                            <p>해당 코드에 등록된 참고 안내가 없습니다.</p>
                          )}
                          <Link to="/knowledge">지식·Runbook 열기 →</Link>
                        </section>
                      </div>
                    )}
                  </td>
                </tr>
              </Fragment>
            );
          })}
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
  const repeats = console2Repeats(views);
  const [repeatMode, setRepeatMode] = useState('device');
  const repeatGroups =
    repeatMode === 'error'
      ? [...new Set(views.map((v) => v.code))]
          .map((code) => views.filter((v) => v.code === code))
          .filter((g) => g.length >= 3)
          .sort((a, b) => b.length - a.length)
      : repeatMode === 'time'
        ? [...repeats].sort((a, b) => b[0].at.getTime() - a[0].at.getTime())
        : repeats;
  const nodes = [...new Set(views.map((v) => JSON.stringify([v.cluster, v.node])))];
  const partial = views.filter((v) => v.rca === 'partial' || v.rca === 'blocked');
  const scopeNote = query.hasNextPage
    ? '불러온 사건 기준 · 추가 자료 확인 중 또는 조회 한도 도달'
    : '선택 범위의 저장 사건 기준';
  return (
    <div className="c2-page c2-dashboard">
      <Heading title="운영 개요" note={`최근 ${period}일 · ${dateTimeText(now)} 기준`}>
        <PeriodButtons period={period} onChange={(v) => setParams({ period: v })} />
        <Link className="button primary" to="/reports/new">
          <FileText size={16} /> 보고서 만들기
        </Link>
      </Heading>
      <QueryState query={query}>
        <div className="c2-context">
          <Activity size={15} />
          <span>{scopeNote}. 저장된 사건이며 현재 장비 상태를 나타내지 않습니다.</span>
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
              '오늘 발생 사건',
              views.filter((v) => dayKey(v.at) === dayKey(now)).length,
              'KST 오늘 발생 시각 기준',
              '/cases?period=1',
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
        <section className="c2-execution-panel" aria-label="사건의 최신 보고서 생성 상태">
          <header>
            <h2>RCA 보고서 생성</h2>
            <span>선택 기간 사건의 최신 실행 기록 · 상태를 선택해 확인</span>
          </header>
          <div className="c2-execution">
            {[...executionStates, 'none'].map((status) => {
              const total = views.filter((v) => (v.executionStatus || 'none') === status).length;
              return (
                <Link
                  key={status}
                  to={`/cases?period=${period}&execution=${status}`}
                  className={`c2-exec-${status}`}
                >
                  <span>
                    <i />
                    {status === 'none' ? '실행 기록 없음' : labels[status]}
                  </span>
                  <strong>{total}</strong>
                </Link>
              );
            })}
          </div>
        </section>
        <IncidentCharts views={views} days={days} period={period} />
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
          <Surface title="반복 발생 탐색" note="장치·오류 조합 또는 오류 코드별 3회 이상">
            <div className="c2-segment" aria-label="반복 탐색 기준">
              {[
                ['device', '장치별'],
                ['error', '오류별'],
                ['time', '최근 발생순'],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={repeatMode === value}
                  onClick={() => setRepeatMode(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="c2-repeat-list">
              {repeatGroups.map((group) => (
                <Link
                  key={console2DeviceKey(group[0])}
                  className="c2-repeat"
                  to={`/cases?period=${period}&${repeatMode === 'error' ? `code=${encodeURIComponent(group[0].code)}` : `device2=${encodeURIComponent(console2DeviceKey(group[0]))}`}`}
                >
                  <div>
                    <b>
                      {repeatMode === 'error'
                        ? group[0].codeText || titleText(group[0])
                        : group[0].node || '노드 미확인'}
                    </b>
                    <small>
                      {repeatMode === 'error'
                        ? `${new Set(group.map((v) => JSON.stringify([v.cluster, v.node]))).size}개 노드`
                        : `${group[0].cluster} · ${group[0].codeText || titleText(group[0])}`}
                    </small>
                    {repeatMode !== 'error' && <code>{group[0].device || '장치 식별 미확인'}</code>}
                    <small>최근 {dateTimeText(group[0].at)}</small>
                  </div>
                  <strong>
                    {group.length}
                    <small>회</small>
                  </strong>
                </Link>
              ))}
            </div>
            {!repeatGroups.length && (
              <p className="c2-empty">같은 대상·오류가 3회 이상 반복된 기록이 없습니다.</p>
            )}
            <Link className="c2-foot-link" to={`/cases?period=${period}&focus=repeat`}>
              반복 사건 확인 →
            </Link>
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
                  <small>
                    {CATEGORIES.map(
                      (c) => `${c.name} ${group.filter((v) => category(v) === c.key).length}`,
                    ).join(' · ')}
                  </small>
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
      <OpsUsage snapshot />
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
    <div className="c2-page c2-cases-page">
      <Heading
        title="RCA 조사"
        note="수신한 사건과 대상 장비를 확인하고, 분석 결과와 런북 안내를 살펴봅니다."
      />
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
        <div className="c2-filters c2-basic-filters">
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
            보고서 생성
            <select
              value={params.get('execution') || ''}
              onChange={(e) => update({ execution: e.target.value })}
            >
              <option value="">전체</option>
              {executionStates.map((status) => (
                <option key={status} value={status}>
                  {labels[status]}
                </option>
              ))}
              <option value="none">실행 기록 없음</option>
            </select>
          </label>
          <label>
            정렬
            <select
              value={params.get('sort') || ''}
              onChange={(e) => update({ sort: e.target.value })}
            >
              <option value="">최신순</option>
              <option value="oldest">오래된 순</option>
              <option value="device">장치별</option>
              <option value="error">오류 코드별</option>
            </select>
          </label>
        </div>
        <details className="c2-advanced-filters">
          <summary>추가 필터</summary>
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
              장치 유형
              <select
                value={params.get('kind') || ''}
                onChange={(e) => update({ kind: e.target.value })}
              >
                <option value="">전체</option>
                <option value="gpu">GPU</option>
                <option value="switch">NVSwitch</option>
                <option value="host">호스트</option>
              </select>
            </label>
            <label>
              오류 유형
              <select
                value={params.get('category') || ''}
                onChange={(e) => update({ category: e.target.value })}
              >
                <option value="">전체</option>
                {CATEGORIES.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
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
            <label>
              반복 발생
              <select
                value={params.get('focus') || ''}
                onChange={(e) => update({ focus: e.target.value })}
              >
                <option value="">전체</option>
                <option value="repeat">3회 이상 반복</option>
              </select>
            </label>
          </div>
        </details>
        <div className="c2-active-filters">
          {[
            ['cluster', '클러스터'],
            ['kind', '장치'],
            ['category', '오류 유형'],
            ['quality', '결과'],
            ['focus', '반복'],
            ['code', '코드'],
          ]
            .filter(([key]) => params.get(key) && (key !== 'focus' || params.get(key) === 'repeat'))
            .map(([key, label]) => (
              <button
                key={key}
                className="c2-filter-chip"
                onClick={() => update({ [key]: '', ...(key === 'cluster' ? { node: '' } : {}) })}
              >
                {label}:{' '}
                {(key === 'category' && CATEGORIES.find((c) => c.key === params.get(key))?.name) ||
                  qualityLabels[params.get(key)!] ||
                  (
                    {
                      gpu: 'GPU',
                      switch: 'NVSwitch',
                      host: '호스트',
                      repeat: '3회 이상',
                      limited: '부분 산출·판단 보류',
                    } as Record<string, string>
                  )[params.get(key)!] ||
                  params.get(key)}{' '}
                ×
              </button>
            ))}
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
  ['c2-ops-insights', '관측 요약'],
  ['c2-report-summary', '지표 비교'],
  ['c2-rca-visual', '관측 비교'],
  ['c2-rca-decision', '사건 판단'],
  ['rca-response-reference', '대응 순서'],
  ['rca-observation-detail', '로그·지표'],
  ['rca-analysis-detail', '분석·근거'],
  ['c2-rca-history', '발생 이력'],
  ['c2-rca-references', '참고 자료'],
  ['namespace-summary-title', 'Namespace 활동'],
  ['c2-hourly-overview', '시간대 요약'],
  ['c2-namespace-charts', '시간대 그래프'],
  ['c2-workloads', '작업 대기·완료'],
  ['incident-summary-title', '사건 기록'],
  ['report-evidence', '집계 근거'],
  ['new-investigation-history', '조사 이력'],
  ['new-incident-state', '처리 상태'],
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
    <div
      className={`c2-reader-layout${location.pathname.startsWith('/reports/') ? ' c2-ops-reader' : ''}`}
    >
      <aside className="c2-toc" aria-label="보고서 탐색">
        <b>목차</b>
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
        <button
          className="text-link"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        >
          처음으로 ↑
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
