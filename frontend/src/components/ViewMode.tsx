import { useApp } from '../lib/store';
export function ViewMode() {
  const app = useApp();
  return (
    <div className="view-switch" role="group" aria-label="GUI 관점 선택">
      {(
        [
          ['classic', '통합 콘솔'],
          ['operations', '신규 콘솔2'],
          ['developer', '개발자'],
          ['new', '신규'],
          ['workbench', '개발 콘솔'],
        ] as const
      ).map(([mode, label]) => (
        <button
          key={mode}
          type="button"
          aria-pressed={app.mode === mode}
          onClick={() => {
            if (mode === app.mode) return;
            const form = document.querySelector('form[data-dirty="true"]');
            if (form && !window.confirm('작성 중인 입력을 두고 화면을 전환할까요?')) return;
            app.setMode(mode);
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
