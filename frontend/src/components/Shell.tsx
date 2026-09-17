import {
  ArrowUpRight,
  Bell,
  BookOpen,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  ChevronsUpDown,
  CircleHelp,
  History,
  Layers,
  LayoutDashboard,
  Menu,
  ScanSearch,
  Server,
  Settings2,
  Sparkles,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { scopeLabel } from '../lib/domain';
import { useApp, useDatabase } from '../lib/store';
import { Assistant } from './assistant';
import { Modal, Notice } from './ui';
const nav = [
  { to: '/dashboard', label: '운영 대시보드', icon: LayoutDashboard },
  { to: '/fleet', label: '자산·관측', icon: Server },
  { to: '/cases', label: 'RCA 조사', icon: ScanSearch },
  { to: '/reports', label: '운영 분석·보고서', icon: ChartNoAxesCombined },
  { to: '/jobs', label: '작업 이력', icon: History },
  { to: '/knowledge', label: '지식·Runbook', icon: BookOpen },
  { to: '/settings', label: '연결·설정', icon: Settings2 },
];
export function Shell() {
  const app = useApp();
  const { reset } = useDatabase();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobile, setMobile] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [profile, setProfile] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [draft, setDraft] = useState(app.scope);
  const [scopeError, setScopeError] = useState('');
  useEffect(() => {
    setMobile(false);
    requestAnimationFrame(() => document.querySelector<HTMLElement>('h1')?.focus());
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const current = nav.find((n) => location.pathname.startsWith(n.to)) || {
    label:
      location.pathname.includes('analys') || location.pathname.includes('incidents')
        ? 'RCA 조사'
        : location.pathname.startsWith('/conversations')
          ? 'Assistant'
          : '운영 분석·보고서',
  };
  const sidebar = (
    <>
      <Link to="/dashboard" className="brand" aria-label="DSX 운영 대시보드">
        <span className="brand-icon">
          <ArrowUpRight size={25} />
        </span>
        <div>
          <strong>
            DSX<span className="brand-period">.</span>
          </strong>
          <span>GPU OPERATIONS</span>
        </div>
      </Link>
      <div className="workspace-label">
        <span className="workspace-logo">D</span>
        <div>
          <b>DSX Workspace</b>
          <small>Infrastructure operations</small>
        </div>
        <ChevronsUpDown size={14} />
      </div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="main-nav" aria-label="주 메뉴">
        {nav.map((n, i) => (
          <NavLink
            key={n.to}
            to={
              n.to === '/fleet' ? '/fleet/assets' : n.to === '/settings' ? '/settings/models' : n.to
            }
            className={() =>
              `nav-item ${location.pathname.startsWith(n.to) || (n.to === '/cases' && /analyses|incidents/.test(location.pathname)) ? 'active' : ''}`
            }
          >
            <n.icon size={19} />
            <span>{n.label}</span>
            {i === 2 && <span className="nav-count">3</span>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="environment">
          <span className="pulse-dot" />
          <span>데모 환경</span>
          <span className="version">v1.1</span>
        </div>
        <button className="help-button" onClick={() => setHelp(true)}>
          <CircleHelp size={17} />
          사용 안내
          <ArrowUpRight size={14} />
        </button>
        <button className="profile" onClick={() => setProfile(true)}>
          <span className="avatar">김</span>
          <span>
            <b>김운영</b>
            <small>
              {
                {
                  operator: '운영자',
                  viewer: '조회자',
                  admin: '서비스 관리자',
                  knowledge: '지식 관리자',
                }[app.role]
              }
            </small>
          </span>
          <ChevronsUpDown size={15} />
        </button>
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
            <span className="breadcrumb-divider">/</span>
            <b>{current.label}</b>
          </div>
          <div className="top-actions">
            <span className="demo-tag">DEMO</span>
            <button
              className="assistant-toggle"
              aria-expanded={app.assistant}
              onClick={() => app.setAssistant(!app.assistant)}
            >
              <Sparkles size={16} />
              Assistant<span className="key-hint">AI</span>
            </button>
            <span className="top-divider" />
            <button
              className="icon-button notification-button"
              aria-label="알림 보기"
              onClick={() => setNotifications(true)}
            >
              <Bell size={19} />
              <i />
            </button>
            <button
              className="avatar small"
              aria-label="사용자 프로필"
              onClick={() => setProfile(true)}
            >
              김
            </button>
          </div>
        </header>
        <div className="scopebar">
          <div className="scope-left">
            <span className="scope-label">관측 범위</span>
            <button
              className="scope-button"
              onClick={() => {
                setDraft(structuredClone(app.scope));
                setScopeError('');
                setScopeOpen(true);
              }}
            >
              <span className="green-dot" />
              {app.scope.clusters.length === 2
                ? '전체 CPC'
                : app.scope.clusters[0]?.cluster_id.toUpperCase()}
              <ChevronDown size={14} />
            </button>
            <div className="scope-chips">
              {app.scope.clusters.map((c) => (
                <span key={c.cluster_id}>
                  {c.cluster_id.toUpperCase()}
                  <span className="chip-divider">/</span>
                  {c.namespaces?.join(', ') || '전체 Namespace'}
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
          </div>
        </div>
        <main id="main-content">
          <Outlet key={app.role} />
        </main>
        <footer className="app-footer">
          <span>
            DSX Operations <span>·</span> 예시 데이터 · 2026.09.16 14:15 KST
          </span>
          <span>관측에서 근거로, 근거에서 판단으로.</span>
        </footer>
      </div>
      {app.assistant && !location.pathname.startsWith('/conversations') && <Assistant />}
      {app.toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {app.toast}
          <button aria-label="알림 닫기" onClick={() => app.notify('')}>
            <X size={15} />
          </button>
        </div>
      )}
      {scopeOpen && (
        <Modal title="관측 범위 선택" onClose={() => setScopeOpen(false)}>
          <p className="muted">
            CPC별 Namespace를 선택합니다. 저장 결과의 범위는 변경되지 않습니다.
          </p>
          <div className="stack">
            {['cpc-1', 'cpc-2'].map((id) => {
              const entry = draft.clusters.find((c) => c.cluster_id === id);
              return (
                <div className="scope-group" key={id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!!entry}
                      onChange={(e) =>
                        setDraft({
                          clusters: e.target.checked
                            ? [...draft.clusters, { cluster_id: id, namespaces: null }]
                            : draft.clusters.filter((c) => c.cluster_id !== id),
                        })
                      }
                    />
                    <b>{id.toUpperCase()}</b>
                    <span className="muted">접근 가능</span>
                  </label>
                  {entry && (
                    <div className="namespace-options">
                      {['전체', 'prod', 'dev', 'research'].map((ns) => (
                        <label className="check" key={ns}>
                          <input
                            type="checkbox"
                            checked={
                              ns === '전체'
                                ? entry.namespaces === null
                                : entry.namespaces?.includes(ns) || false
                            }
                            onChange={(e) =>
                              setDraft({
                                clusters: draft.clusters.map((c) =>
                                  c.cluster_id === id
                                    ? {
                                        ...c,
                                        namespaces:
                                          ns === '전체'
                                            ? null
                                            : e.target.checked
                                              ? [...(c.namespaces || []), ns]
                                              : (c.namespaces || []).filter((n) => n !== ns),
                                      }
                                    : c,
                                ),
                              })
                            }
                          />
                          {ns}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {scopeError && (
              <p role="alert" className="error">
                {scopeError}
              </p>
            )}
            <button
              className="button primary"
              onClick={() => {
                if (
                  !draft.clusters.length ||
                  draft.clusters.some((c) => c.namespaces?.length === 0)
                ) {
                  setScopeError('CPC와 하나 이상의 Namespace를 선택해 주세요.');
                  return;
                }
                app.setScope(draft);
                setScopeOpen(false);
              }}
            >
              선택 범위 적용
            </button>
          </div>
        </Modal>
      )}
      {help && (
        <Modal title="DSX 프론트엔드 안내" onClose={() => setHelp(false)}>
          <div className="stack">
            <Notice>
              백엔드와 연결되지 않은 프론트엔드 데모입니다. 실제 장비나 모델에 요청하지 않습니다.
            </Notice>
            <p>
              운영 대시보드에서 자산을 선택하고, RCA 조사 또는 운영 보고서를 요청해 보세요. 데모
              작업은 접수 → 실행 → 결과 저장 흐름을 재현합니다.
            </p>
            <p>
              생성한 데모 작업·일정·지식·대화는 이 브라우저에 저장되어 새로고침 후에도 확인할 수
              있습니다. 실제 업무 저장소와 구분됩니다.
            </p>
            <p>
              모든 시각은 Asia/Seoul 기준입니다. 수집 지연과 근거 부족은 정상 값 0과 구분해
              표시합니다.
            </p>
            <Link className="button" to="/fleet/quality" onClick={() => setHelp(false)}>
              관측 상태 살펴보기
              <ArrowUpRight size={15} />
            </Link>
            <button
              className="button"
              onClick={() => {
                setHelp(false);
                setResetOpen(true);
              }}
            >
              데모 데이터 초기화
            </button>
          </div>
        </Modal>
      )}
      {resetOpen && (
        <Modal title="데모 데이터 초기화" onClose={() => setResetOpen(false)}>
          <div className="stack">
            <Notice>
              이 브라우저에서 만든 데모 데이터를 초기 예시로 되돌립니다. 실제 서버 데이터에는 영향이
              없습니다.
            </Notice>
            <div className="form-actions">
              <button className="button" onClick={() => setResetOpen(false)}>
                돌아가기
              </button>
              <button
                className="button primary"
                onClick={async () => {
                  await reset();
                  setResetOpen(false);
                  app.setAssistant(false);
                  navigate('/dashboard');
                  app.notify('데모 데이터를 초기 예시로 되돌렸습니다.');
                }}
              >
                초기 예시로 복원
              </button>
            </div>
          </div>
        </Modal>
      )}
      {profile && (
        <Modal title="데모 사용자" onClose={() => setProfile(false)}>
          <div className="stack">
            <p>김운영 · operations@example.internal</p>
            <label className="field">
              <span>화면 확인용 역할</span>
              <select
                value={app.role}
                onChange={(e) => {
                  app.setRole(e.target.value);
                  setProfile(false);
                }}
              >
                <option value="operator">운영자</option>
                <option value="viewer">조회자</option>
                <option value="knowledge">지식 관리자</option>
                <option value="admin">서비스 관리자</option>
              </select>
            </label>
            <Notice>
              역할 선택은 UI 확인용입니다. 실제 인증·grant 검증은 서버 통합 대상입니다.
            </Notice>
            <small>{scopeLabel(app.scope)}</small>
          </div>
        </Modal>
      )}
      {notifications && (
        <Modal title="운영 알림" onClose={() => setNotifications(false)}>
          <div className="notification-list">
            <Link to={`/cases`} onClick={() => setNotifications(false)}>
              <span className="notification-marker warning" />
              <div>
                <b>우선 검토가 필요한 사건 3건</b>
                <p>Xid 오류와 온도·ECC 관측을 확인하세요.</p>
                <small>고정 스냅샷 · 14:15 KST</small>
              </div>
            </Link>
            <Link to="/fleet/quality" onClick={() => setNotifications(false)}>
              <span className="notification-marker" />
              <div>
                <b>dgx-08 수신 지연</b>
                <p>마지막 수신 14:03 · 현재 장비 상태 미확인</p>
              </div>
            </Link>
          </div>
        </Modal>
      )}
    </div>
  );
}
