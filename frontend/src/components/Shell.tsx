import {
  BookOpen,
  ChartNoAxesCombined,
  ChevronDown,
  History,
  Layers,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ScanSearch,
  Server,
  Settings2,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, matchPath } from 'react-router-dom';
import { obj, useResource } from '../lib/live';
import { reportScopeClusters } from '../lib/workflow';
import { reportTabs } from '../lib/reportNavigation';
import { scopeLabel } from '../lib/domain';
import { returnPath } from '../lib/debug';
import { useApp } from '../lib/store';
import { QueryState } from './live';
import { Empty, Field, Modal, NavTabs, PageHead } from './ui';
import { NewWorkspace } from '../pages/NewWorkspace';
import { ConsoleWorkspace } from '../pages/ConsoleWorkspace';
import { Console2 } from '../pages/Console2';
import { ViewMode } from './ViewMode';
import { ApiInspector, DeveloperContext } from './DeveloperContext';
const nav = [
  { to: '/dashboard', label: '운영 대시보드', icon: LayoutDashboard },
  { to: '/fleet/assets', label: '자산·관측', icon: Server },
  { to: '/cases', label: 'RCA 조사', icon: ScanSearch },
  { to: '/reports', label: '운영 분석·보고서', icon: ChartNoAxesCombined },
  { to: '/jobs', label: '작업 이력', icon: History },
  { to: '/knowledge', label: '지식·Runbook', icon: BookOpen },
  { to: '/settings/models', label: '연결·설정', icon: Settings2 },
];
// The unified console: job history opens from each RCA report instead of its own menu.
const consoleNav = [
  { to: '/dashboard', label: '운영 대시보드', icon: LayoutDashboard },
  { to: '/cases', label: 'RCA 조사', icon: ScanSearch },
  { to: '/reports', label: 'Ops 보고서', icon: ChartNoAxesCombined },
  { to: '/knowledge', label: '지식·Runbook', icon: BookOpen },
  { to: '/fleet/assets', label: '자산·관측', icon: Server },
  { to: '/settings/models', label: '연결·설정', icon: Settings2 },
];
export function Shell() {
  const app = useApp(),
    location = useLocation(),
    me = app.connection;
  const consoleMode = app.mode === 'workbench' || app.mode === 'classic';
  const reportId = matchPath('/reports/:id', location.pathname)?.params.id;
  const isSavedReport = !!reportId && reportId !== 'new';
  const report = useResource(isSavedReport ? `/reports/${reportId}` : null, undefined, true);
  const savedScope = reportScopeClusters(obj(report.data?.result ?? report.data));
  const isGuide = location.pathname === '/operator-guide';
  const isJobHistory = location.pathname === '/jobs' || location.pathname.startsWith('/jobs/');
  const names =
    app.mode === 'workbench'
      ? ['실패 진단', '자산·관측', '사건·RCA', 'Ops 보고서', '전체 작업', 'Runbook', '연결·설정']
      : app.mode === 'operations'
        ? [
            '오늘의 운영',
            '자산 탐색',
            '사건 대응',
            '분석 서재',
            '요청 진행',
            '운영 지식',
            '환경 관리',
          ]
        : app.mode === 'developer'
          ? [
              '처리 흐름·검증',
              '관측·신원',
              '사건·RCA',
              '보고서·일정',
              '작업 디버깅',
              'Runbook·revision',
              '연결·구성',
            ]
          : nav.map((n) => n.label);
  const menus =
    app.mode === 'classic' || app.mode === 'operations'
      ? consoleNav
      : app.mode === 'new'
        ? [
            { ...nav[0], label: '운영 현황' },
            { ...nav[2], label: '사건 분석' },
            { ...nav[3], label: '운영 보고서' },
          ]
        : nav.map((n, i) => ({ ...n, label: names[i] }));
  const [mobile, setMobile] = useState(false),
    [scopeOpen, setScopeOpen] = useState(false),
    [draft, setDraft] = useState(app.scope),
    [scopeError, setScopeError] = useState('');
  const [debugReturn, setDebugReturn] = useState('');
  const isConfiguration = /^\/(settings|knowledge)(\/|$)/.test(location.pathname);
  useEffect(() => {
    const from = returnPath(obj(location.state).from, '');
    if (isConfiguration && /^\/jobs\/[^/?#]+/.test(from)) setDebugReturn(from);
    else if (!isConfiguration) setDebugReturn('');
  }, [isConfiguration, location.pathname, location.state]);
  useEffect(() => {
    setMobile(false);
    window.scrollTo(0, 0);
    requestAnimationFrame(() => {
      // The report list restores focus to the selected report on return.
      if (
        location.pathname === '/reports' &&
        document.activeElement?.closest('[id^="report-row-"]')
      )
        return;
      document.querySelector<HTMLElement>('h1')?.focus({ preventScroll: true });
    });
  }, [location.pathname]);
  const active = (to: string) =>
    location.pathname.startsWith(to.split('/').slice(0, 2).join('/')) ||
    (to === '/cases' && /analyses|incidents/.test(location.pathname)) ||
    (to === '/reports' && (isGuide || location.pathname.startsWith('/schedules')));
  const sidebar = (
    <>
      <Link to="/dashboard" className="brand">
        <span className="brand-icon turtle-brand">
          <img src="/turtle-mark.png" alt="" />
        </span>
        <div>
          <strong>GPU Ops Advisor</strong>
          <span>GPU OPERATIONS</span>
        </div>
      </Link>
      <div className="workspace-label">
        <span className="workspace-logo">G</span>
        <div>
          <b>GPU Ops Advisor</b>
          <small>Infrastructure operations</small>
        </div>
      </div>

      <nav className="main-nav" aria-label="주 메뉴">
        {menus.map((n) => (
          <Link
            key={n.to}
            to={n.to}
            className={`nav-item ${active(n.to) ? 'active' : ''}`}
            aria-current={active(n.to) ? 'page' : undefined}
          >
            <n.icon size={19} />
            <span>{n.label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="environment">
          <span className={app.ready ? 'pulse-dot' : ''} />
          <span>
            {app.ready
              ? app.mode === 'new' || app.mode === 'classic' || app.mode === 'operations'
                ? '조회 API 연결됨'
                : '로컬 API 연결'
              : '연결 확인 중'}
          </span>
          <span className="version">v1.3</span>
        </div>
        {app.mode !== 'new' && (
          <div className="profile">
            <span className="avatar">D</span>
            <span>
              <b>{app.ready ? 'GPU Operations' : '연결 확인 중'}</b>
              <small>개발 환경 · 인증 제외</small>
            </span>
          </div>
        )}
      </div>
    </>
  );
  return (
    <div
      className={`app-shell view-${app.mode}${consoleMode ? ' console-shell' : ''}${app.mode === 'operations' ? ' console2-shell' : ''}`}
    >
      <a href="#main-content" className="skip-link">
        본문으로 이동
      </a>
      <aside className="sidebar">{sidebar}</aside>
      {mobile && (
        <Modal title="메뉴" onClose={() => setMobile(false)}>
          <div className="mobile-nav">{sidebar}</div>
        </Modal>
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="메뉴 열기"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <Layers size={17} />
            <span>
              {app.mode === 'workbench'
                ? 'DEVELOPER'
                : app.mode === 'classic' || app.mode === 'operations'
                  ? 'OPERATIONS'
                  : 'Workspace'}
            </span>
            <span>/</span>
            <b>{menus.find((n) => active(n.to))?.label || '업무 상세'}</b>
          </div>
          <div className="top-actions">
            <ViewMode />
          </div>
        </header>
        {!isGuide &&
          ((app.mode !== 'new' && app.mode !== 'classic' && app.mode !== 'operations') ||
            (app.mode === 'operations' && isJobHistory) ||
            ['/dashboard', '/cases', '/reports', '/reports/new', '/schedules'].includes(
              location.pathname,
            )) && (
            <div className="scopebar">
              {isSavedReport ? (
                <>
                  <div className="scope-left">
                    <span className="scope-label">이 보고서의 분석 범위</span>
                    <div className="scope-chips">
                      {savedScope.length ? (
                        savedScope.map(({ cluster, namespaces }) => (
                          <span key={cluster}>
                            {cluster} / {namespaces}
                          </span>
                        ))
                      ) : (
                        <span>{report.isPending ? '불러오는 중' : '분석 범위 미확인'}</span>
                      )}
                    </div>
                  </div>
                  <span className="muted">생성 당시 범위 · 분석 기간은 본문에 표시</span>
                </>
              ) : (
                <>
                  <div className="scope-left">
                    <span className="scope-label">관측 범위</span>
                    <button
                      className="scope-button"
                      disabled={!app.ready || !app.registeredScope.clusters.length}
                      onClick={() => {
                        setDraft(structuredClone(app.scope));
                        setScopeError('');
                        setScopeOpen(true);
                      }}
                    >
                      {app.scope.clusters.length}개 CPC
                      <ChevronDown size={14} />
                    </button>
                    <div className="scope-chips">
                      {app.scope.clusters.map((c) => (
                        <span key={c.cluster_id}>
                          {c.cluster_id.toUpperCase()} /{' '}
                          {c.namespaces?.join(', ') || '전체 Namespace'}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="scope-right">
                    <span className="time-zone">Asia/Seoul</span>
                    {!isJobHistory &&
                      app.mode !== 'workbench' &&
                      app.mode !== 'classic' &&
                      app.mode !== 'operations' &&
                      !location.pathname.startsWith('/reports') &&
                      (app.mode !== 'new' ||
                        ['/dashboard', '/cases'].includes(location.pathname)) && (
                        <select
                          aria-label="조회 기간"
                          value={app.period}
                          onChange={(e) => app.setPeriod(e.target.value)}
                        >
                          <option value="1h">최근 1시간</option>
                          <option value="6h">최근 6시간</option>
                          <option value="24h">최근 24시간</option>
                        </select>
                      )}
                    <button
                      className="icon-button"
                      aria-label="데이터 새로고침"
                      onClick={app.refresh}
                    >
                      <RefreshCw size={17} />
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        <main id="main-content">
          {app.mode === 'workbench' && isConfiguration && debugReturn && (
            <div className="console-return">
              <Link className="button" to={debugReturn}>
                ← 조사 중인 작업으로
              </Link>
              <span>현재 설정 화면 · 작업 당시 설정은 고정 revision으로 확인</span>
            </div>
          )}
          {app.mode === 'developer' && <DeveloperContext />}
          {app.mode !== 'new' &&
            location.pathname === '/reports' &&
            (me.isPending || me.isError || !app.registeredScope.clusters.length) && (
              <div className="live-padding">
                <NavTabs items={reportTabs} />
              </div>
            )}
          {app.mode === 'new' && isGuide ? (
            <NewWorkspace />
          ) : app.mode === 'new' ? (
            <QueryState query={me}>
              <NewWorkspace />
            </QueryState>
          ) : isGuide ? (
            <Outlet />
          ) : (
            <QueryState query={me}>
              {!app.registeredScope.clusters.length &&
              !location.pathname.startsWith('/settings') &&
              !location.pathname.startsWith('/knowledge') ? (
                <div className="page">
                  <PageHead
                    eyebrow="GET STARTED"
                    title="클러스터 등록"
                    description="분석할 클러스터를 등록해 시작하세요."
                  />
                  <Empty
                    title="등록된 클러스터가 없습니다."
                    description="클러스터를 등록하면 관측 범위를 선택하고 분석을 요청할 수 있습니다."
                    action={
                      <Link className="button primary" to="/settings/data">
                        클러스터 등록하기
                      </Link>
                    }
                  />
                </div>
              ) : app.mode === 'operations' ? (
                <Console2 />
              ) : consoleMode ? (
                <ConsoleWorkspace />
              ) : (
                <Outlet />
              )}
            </QueryState>
          )}
          {(app.mode === 'developer' || app.mode === 'workbench') && <ApiInspector />}
        </main>
        <footer className="app-footer">
          <span>
            {app.mode === 'new' || app.mode === 'classic' || app.mode === 'operations'
              ? 'GPU Ops Advisor'
              : 'GPU Ops Advisor · Go API · PostgreSQL'}
          </span>
          <span>
            {consoleMode || app.mode === 'operations'
              ? 'Asia/Seoul · 저장된 관측 자료 기준'
              : '관측에서 근거로, 근거에서 판단으로.'}
          </span>
        </footer>
      </div>
      {app.toast && (
        <div className="toast" role="status">
          {app.toast}
          <button aria-label="알림 닫기" onClick={() => app.notify('')}>
            <X size={15} />
          </button>
        </div>
      )}
      {scopeOpen && (
        <Modal title="관측 범위 선택" onClose={() => setScopeOpen(false)}>
          <p className="muted">등록된 CPC의 Namespace 범위를 선택합니다.</p>
          <div className="stack">
            {app.registeredScope.clusters.map((c) => {
              const entry = draft.clusters.find((d) => d.cluster_id === c.cluster_id);
              return (
                <div className="scope-group" key={c.cluster_id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!!entry}
                      onChange={(e) =>
                        setDraft({
                          clusters: e.target.checked
                            ? [...draft.clusters, c]
                            : draft.clusters.filter((d) => d.cluster_id !== c.cluster_id),
                        })
                      }
                    />
                    {c.cluster_id.toUpperCase()}
                  </label>
                  {entry && (
                    <Field
                      label="Namespace"
                      hint={
                        c.namespaces
                          ? 'Namespace: ' + c.namespaces.join(', ')
                          : '전체 Namespace는 비워 두세요. 여러 개는 쉼표로 구분합니다.'
                      }
                    >
                      <input
                        value={entry.namespaces?.join(',') || ''}
                        onChange={(e) =>
                          setDraft({
                            clusters: draft.clusters.map((d) =>
                              d.cluster_id === c.cluster_id
                                ? {
                                    ...d,
                                    namespaces: e.target.value ? e.target.value.split(',') : null,
                                  }
                                : d,
                            ),
                          })
                        }
                      />
                    </Field>
                  )}
                </div>
              );
            })}
            {scopeError && (
              <p className="error" role="alert">
                {scopeError}
              </p>
            )}
            <button
              className="button primary"
              onClick={() => {
                const normalized = {
                  clusters: draft.clusters.map((c) => ({
                    ...c,
                    namespaces: c.namespaces?.map((n) => n.trim()).filter(Boolean) || null,
                  })),
                };
                const allowed = app.registeredScope;
                if (
                  !normalized.clusters.length ||
                  normalized.clusters.some((c) => {
                    const g = allowed.clusters.find((a) => a.cluster_id === c.cluster_id);
                    return (
                      !g ||
                      c.namespaces?.length === 0 ||
                      (g.namespaces !== null &&
                        (c.namespaces === null ||
                          c.namespaces.some((n) => !g.namespaces!.includes(n))))
                    );
                  })
                ) {
                  setScopeError('등록된 CPC·Namespace를 선택해 주세요.');
                  return;
                }
                app.setScope(normalized);
                setScopeOpen(false);
              }}
            >
              선택 범위 적용
            </button>
            <small>{scopeLabel(draft)}</small>
          </div>
        </Modal>
      )}
    </div>
  );
}
