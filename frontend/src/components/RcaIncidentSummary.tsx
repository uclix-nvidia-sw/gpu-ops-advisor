import { obj, rows, str, num, type Row } from '../lib/live';
const formatDate = (value: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(value)) + ' KST';

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
  return (
    <section className="rca-narrative-problem" aria-label="사건 핵심 요약">
      <h4>
        1. 사건 요약 ·{str(target.node) || str(target.machine_id)} ·{' '}
        {codes.join(', ') || '장애 알림'}
      </h4>
      <p>{[...new Set(logs.map((r) => str(r.device)).filter(Boolean))].join(', ')}</p>
      {times.length > 0 && (
        <p>
          <strong>로그 보고 구간:</strong> {formatDate(times[0])} ~{' '}
          {formatDate(times[times.length - 1])}
        </p>
      )}
      <p>
        수신 기록 {logs.reduce((total, r) => total + num(r.reports), 0)}건 · 관련 지표{' '}
        {new Set(rows(view.metrics).map((m) => str(m.name))).size}종. 보고 구간은 로그에 기록된
        처음·마지막 시각입니다.
      </p>
    </section>
  );
}
