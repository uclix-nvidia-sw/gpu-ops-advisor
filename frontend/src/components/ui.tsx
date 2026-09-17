import { ArrowUpRight, Inbox, Info, Search, X } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { labels } from '../lib/domain';
export function Badge({ status, label }: { status: string | null; label?: string }) {
  return (
    <span className={`badge badge-${status || 'neutral'}`}>
      <span className="status-dot" />
      {label || (status ? labels[status] || status : '결과 미확정')}
    </span>
  );
}
export function PageHead({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 tabIndex={-1}>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="head-actions">{actions}</div>
    </div>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = '',
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-head">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function NavTabs({ items }: { items: { label: string; to: string }[] }) {
  return (
    <nav className="tabs" aria-label="하위 메뉴">
      {items.map((i) => (
        <Link key={i.to} className={location.pathname === i.to ? 'active' : ''} to={i.to}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: string }) {
  return (
    <div className={`notice notice-${tone}`}>
      <Info size={17} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title = '조회 결과가 없습니다.',
  description = '검색어나 필터를 변경해 다시 확인해 주세요.',
  action,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={32} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function SearchBox({
  value,
  onChange,
  placeholder = '이름 또는 ID 검색',
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-box">
      <Search size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="검색 지우기" onClick={() => onChange('')}>
          <X size={14} />
        </button>
      )}
    </div>
  );
}
export function TextLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="text-link" to={to}>
      {children}
      <ArrowUpRight size={15} />
    </Link>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Modal({
  title,
  onClose,
  children,
  wide = false,
  confirmClose,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  confirmClose?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [confirming, setConfirming] = useState(false);
  const requestClose = () => (confirmClose ? setConfirming(true) : onClose());
  const closeRef = useRef(onClose);
  closeRef.current = requestClose;
  useEffect(() => {
    const prior = document.activeElement as HTMLElement;
    const dialog = ref.current!;
    dialog.showModal();
    const onCancel = (e: Event) => {
      e.preventDefault();
      closeRef.current();
    };
    dialog.addEventListener('cancel', onCancel);
    return () => {
      dialog.removeEventListener('cancel', onCancel);
      dialog.close();
      prior?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'modal-wide' : ''}`}
      aria-label={title}
      onClick={(e) => {
        if (e.target === ref.current) requestClose();
      }}
    >
      <div className="modal-inner">
        <header>
          <h2>{title}</h2>
          <button className="icon-button" aria-label="닫기" onClick={requestClose}>
            <X size={20} />
          </button>
        </header>
        {confirming && (
          <div className="stack">
            <Notice tone="warning">{confirmClose}</Notice>
            <div className="form-actions">
              <button className="button" onClick={() => setConfirming(false)}>
                계속 편집
              </button>
              <button className="button danger" onClick={onClose}>
                변경 버리고 닫기
              </button>
            </div>
          </div>
        )}
        <div hidden={confirming}>{children}</div>
      </div>
    </dialog>
  );
}
