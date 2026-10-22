/** RCA chronology keeps seconds and states the timezone; raw evidence retains full precision. */
export function formatRcaTime(value: string) {
  if (!Number.isFinite(Date.parse(value))) return '—';
  return (
    new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(value)) + ' KST'
  );
}
