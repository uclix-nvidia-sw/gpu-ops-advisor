import { reportScopeClusters } from '../lib/workflow';
import { num, obj, rows, str, type Row } from '../lib/live';
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

export function ReportExecution({ job }: { job: Row }) {
  const pending: Record<string, string> = {
    queued: '아직 실행 전',
    running: '실행 중 · 완료 후 표시',
    retry_wait: '재시도 대기 · 완료 후 표시',
    failed: '보고서 생성 실패',
    cancelled: '보고서 생성 취소',
    expired: '보고서 생성 기한 만료',
  };
  if (pending[str(job.status)]) return <span>{pending[str(job.status)]}</span>;
  const attempts = rows(job.attempts).sort((a, b) => num(a.attempt_no) - num(b.attempt_no));
  const spans = attempts.map((attempt) => ({
    start: Date.parse(str(attempt.started_at)),
    end: Date.parse(str(attempt.ended_at)),
  }));
  if (
    job.status !== 'succeeded' ||
    !attempts.length ||
    attempts.length !== num(job.attempt_no) ||
    spans.some(
      ({ start, end }, i) =>
        num(attempts[i].attempt_no) !== i + 1 ||
        !Number.isFinite(start) ||
        !Number.isFinite(end) ||
        end < start ||
        (i > 0 && start < spans[i - 1].end),
    )
  )
    return <span>실행시간 미확인</span>;
  const elapsed = spans.reduce((total, { start, end }) => total + end - start, 0);
  const created = Date.parse(str(job.created_at));
  const total =
    Number.isFinite(created) && created <= spans[0].start
      ? spans[spans.length - 1].end - created
      : null;
  const duration = (ms: number) => {
    if (ms > 0 && ms < 1000) return '1초 미만';
    const seconds = Math.round(ms / 1000);
    return [
      seconds >= 3600 ? `${Math.floor(seconds / 3600)}시간` : '',
      seconds >= 60 ? `${Math.floor((seconds % 3600) / 60)}분` : '',
      `${seconds % 60}초`,
    ]
      .filter(Boolean)
      .join(' ');
  };
  return (
    <div>
      <strong>{duration(elapsed)}</strong>
      <div className="muted">
        대기 제외{attempts.length > 1 ? ` · ${attempts.length}회 시도 합계` : ''}
      </div>
      <div className="muted">
        접수부터 완료까지 {total === null ? '미확인' : duration(total)} · 대기 포함
      </div>
    </div>
  );
}
