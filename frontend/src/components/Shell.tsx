import {
  ArrowUpRight,
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
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { scopeLabel } from '../lib/domain';
import { useApp } from '../lib/store';
import { QueryState } from './live';
import { Empty, Field, Modal, PageHead } from './ui';
const nav = [
  { to: '/dashboard', label: '운영 대시보드', icon: LayoutDashboard },
  { to: '/fleet/assets', label: '자산·관측', icon: Server },
  { to: '/cases', label: 'RCA 조사', icon: ScanSearch },
  { to: '/reports', label: '운영 분석·보고서', icon: ChartNoAxesCombined },
  { to: '/jobs', label: '작업 이력', icon: History },
  { to: '/knowledge', label: '지식·Runbook', icon: BookOpen },
  { to: '/settings/models', label: '연결·설정', icon: Settings2 },
];
export function Shell() {
  const app = useApp(),
    location = useLocation(),
    me = app.connection;
  const [mobile, setMobile] = useState(false),
    [scopeOpen, setScopeOpen] = useState(false),
    [draft, setDraft] = useState(app.scope),
    [scopeError, setScopeError] = useState('');
  useEffect(() => {
    setMobile(false);
    window.scrollTo(0, 0);
    requestAnimationFrame(() => document.querySelector<HTMLElement>('h1')?.focus());
  }, [location.pathname]);
  const active = (to: string) =>
    location.pathname.startsWith(to.split('/').slice(0, 2).join('/')) ||
    (to === '/cases' && /analyses|incidents/.test(location.pathname)) ||
    (to === '/reports' && location.pathname.startsWith('/schedules'));
  const sidebar = (
    <>
      <Link to="/dashboard" className="brand">
        <span className="brand-icon">
          <ArrowUpRight size={25} />
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
      <div className="nav-label">WORKSPACE</div>
      <nav className="main-nav" aria-label="주 메뉴">
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} className={`nav-item ${active(n.to) ? 'active' : ''}`}>
            <n.icon size={19} />
            <span>{n.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="environment">
          <span className={app.ready ? 'pulse-dot' : ''} />
          <span>{app.ready ? '로컬 API 연결' : '연결 확인 중'}</span>
          <span className="version">v1.3</span>
        </div>
        <div className="profile">
          <span className="avatar">D</span>
          <span>
            <b>{app.ready ? 'GPU Operations' : '연결 확인 중'}</b>
            <small>개발 환경 · 인증 제외</small>
          </span>
        </div>
      </div>
    </>
  );
  return (
    <div className="app-shell">
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
            <span>Workspace</span>
            <span>/</span>
            <b>{nav.find((n) => active(n.to))?.label || '업무 상세'}</b>
          </div>
          <div className="top-actions">
            <span className="environment-tag">LOCAL API</span>
          </div>
        </header>
        <div className="scopebar">
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
                  {c.cluster_id.toUpperCase()} / {c.namespaces?.join(', ') || '전체 Namespace'}
                </span>
              ))}
            </div>
          </div>
          <div className="scope-right">
            <span className="time-zone">Asia/Seoul</span>
            <select
              aria-label="조회 기간"
              value={app.period}
              onChange={(e) => app.setPeriod(e.target.value)}
            >
              <option value="1h">최근 1시간</option>
              <option value="6h">최근 6시간</option>
              <option value="24h">최근 24시간</option>
            </select>
            <button className="icon-button" aria-label="데이터 새로고침" onClick={app.refresh}>
              <RefreshCw size={17} />
            </button>
          </div>
        </div>
        <main id="main-content">
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
            ) : (
              <Outlet />
            )}
          </QueryState>
        </main>
        <footer className="app-footer">
          <span>GPU Ops Advisor · Go API · PostgreSQL</span>
          <span>관측에서 근거로, 근거에서 판단으로.</span>
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
