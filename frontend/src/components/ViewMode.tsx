import { useApp } from '../lib/store';
export function ViewMode() {
  const app = useApp();
  return (
    <div className="view-switch" role="group" aria-label="GUI 관점 선택">
      {(
        [
          ['classic', '기존'],
          ['operations', '운영측'],
          ['developer', '개발측'],
        ] as const
      ).map(([mode, label]) => (
        <button
          key={mode}
          type="button"
          aria-pressed={app.mode === mode}
          onClick={() => app.setMode(mode)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
