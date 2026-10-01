import { CalendarClock, MousePointer2, CircleHelp } from 'lucide-react';

export function ReportOrigin({ value }: { value: unknown }) {
  const kind = value === 'schedule' || value === 'manual' ? value : 'unknown';
  const Icon = kind === 'schedule' ? CalendarClock : kind === 'manual' ? MousePointer2 : CircleHelp;
  const label =
    kind === 'schedule' ? '자동 생성' : kind === 'manual' ? '직접 요청' : '생성 방식 미확인';
  return (
    <span className={`report-origin report-origin-${kind}`} aria-label={`생성 방식: ${label}`}>
      <Icon size={16} aria-hidden="true" />
      {label}
    </span>
  );
}
export function ReportTimeNote() {
  return <p className="report-time-note">모든 시각은 한국 시간 기준입니다.</p>;
}
