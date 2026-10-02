import { reportScopeClusters } from '../lib/workflow';
import { obj, str, type Row } from '../lib/live';
import { reportPeriodLabel, reportRequestTime } from '../lib/reportPeriod';
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

export function ReportPeriod({ value }: { value: unknown }) {
  const range = obj(value),
    start = str(range.start),
    end = str(range.end);
  const valid =
    Number.isFinite(Date.parse(start)) &&
    Number.isFinite(Date.parse(end)) &&
    Date.parse(end) > Date.parse(start);
  return (
    <div className="report-period">
      <span>{reportPeriodLabel(start, end)}</span>
      {valid && (
        <details>
          <summary>정확한 시간 범위</summary>
          <p>
            {reportRequestTime(start)}부터 {reportRequestTime(end)} 직전까지
          </p>
          <p>분석 대상 데이터의 기간입니다. 보고서 생성에 걸린 시간이 아닙니다.</p>
        </details>
      )}
    </div>
  );
}

export function ReportScope({ job }: { job: Row }) {
  const clusters = reportScopeClusters(job);
  if (!clusters.length) return <span>분석 대상 미확인</span>;
  return (
    <ul className="report-scope" aria-label="클러스터별 분석 대상">
      {clusters.map(({ cluster, namespaces }, index) => (
        <li key={index}>
          <div>
            <span className="report-scope-label">클러스터</span>
            <strong>{cluster}</strong>
          </div>
          <div>
            <span className="report-scope-label">Namespace 범위</span>
            <span>{namespaces}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
