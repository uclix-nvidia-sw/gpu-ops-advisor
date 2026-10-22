import { obj, rows, str, strings, type Row } from '../lib/live';
import { formatRcaTime as formatDate } from '../lib/rcaTime';

export function RcaIncidentSummary({ result }: { result: Row }) {
  const view = obj(obj(result.quality).triage_observations);
  if (view.schema !== 'rca-triage-observations/1') return null;
  const logs = rows(view.logs);
  const target = obj(view.target);
  const codes = [...new Set(logs.map((r) => str(r.code).toUpperCase()))];
  const times = logs
    .flatMap((r) => [str(r.first), str(r.last)])
    .filter((v) => Number.isFinite(Date.parse(v)))
    .sort((a, b) => Date.parse(a) - Date.parse(b));
  const eventTimes = [...new Set(logs.flatMap((r) => strings(r.event_times)))]
    .filter((v) => Number.isFinite(Date.parse(v)))
    .sort();
  const guidance = rows(obj(result.quality).runbook_guidance).filter(
    (g) => g.report_applicability !== 'reference_only',
  );
  return (
    <section className="rca-narrative-problem" aria-label="사건 핵심 요약">
      <h4>
        1. 사건 요약 ·{str(target.node) || str(target.machine_id)} ·{' '}
        {codes.join(', ') || '장애 알림'}
      </h4>
      <p>{[...new Set(logs.map((r) => str(r.device)).filter(Boolean))].join(', ')}</p>
      {eventTimes.length > 0 && (
        <p>
          <strong>오류 발생:</strong> {eventTimes.map(formatDate).join(', ')}
        </p>
      )}
      {times.length > 0 && (
        <p>
          <strong>로그 보고 구간:</strong> {formatDate(times[0])} ~{' '}
          {formatDate(times[times.length - 1])}
        </p>
      )}
      {guidance.map((g, i) => (
        <p key={i}>
          {str(obj(g.guidance).meaning)} 우선 대응:{' '}
          {str(
            rows(obj(g.guidance).next_checks).find(
              (c) => !str(c.title).startsWith('알림이 가리키는'),
            )?.title,
          )}
        </p>
      ))}
    </section>
  );
}
