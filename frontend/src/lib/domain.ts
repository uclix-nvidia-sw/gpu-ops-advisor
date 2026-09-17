import type { Scope, TimeRange } from './types';
export const labels: Record<string, string> = {
  ready: '산출 가능',
  partial: '부분 산출',
  blocked: '근거 부족',
  not_applicable: '적용 대상 아님',
  queued: '접수 대기',
  running: '실행 중',
  retry_wait: '재시도 대기',
  succeeded: '실행 완료',
  failed: '실행 실패',
  cancelled: '취소 완료',
  expired: '기한 만료',
  healthy: '정상 관측',
  warning: '주의',
  critical: '긴급',
  delayed: '수신 지연',
  open: '열림',
  investigating: '조사 중',
  resolved: '해결됨',
  closed: '종결',
  bound: '노드 배치됨',
  unbound: '노드 미배치',
  unknown: '미확인',
  matched: 'GPU 연결 확인',
  ambiguous: '연결 후보 여러 개',
  not_observed: '연결 미관측',
  active_observed: '활동 관측',
  low_activity_candidate: '저활동 검토 후보',
  insufficient_data: '활동 근거 부족',
  draft: '초안',
  in_review: '검토 중',
  reviewed: '검토 완료',
  published: '발행됨',
  retired: '폐기됨',
  daily: '매일',
  weekly: '매주',
  monthly: '매월',
};
export const scopeLabel = (scope: Scope) =>
  scope.clusters
    .map(
      (c) =>
        `${c.cluster_id.toUpperCase()}${c.namespaces ? ' / ' + c.namespaces.join(', ') : ' / 전체 Namespace'}`,
    )
    .join(' · ');
export const inScope = (scope: Scope, cluster: string, namespace?: string) =>
  scope.clusters.some(
    (c) =>
      c.cluster_id === cluster &&
      (namespace === undefined || c.namespaces === null || c.namespaces.includes(namespace)),
  );
export const formatDate = (date: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(date));
export function calendarRange(start: string, end: string): TimeRange {
  const from = new Date(`${start}T00:00:00+09:00`);
  const until = new Date(`${end}T00:00:00+09:00`);
  until.setUTCDate(until.getUTCDate() + 1);
  if (!Number.isFinite(+from) || !Number.isFinite(+until) || +from >= +until)
    throw new Error('종료일은 시작일과 같거나 이후여야 합니다.');
  return { start: from.toISOString(), end: until.toISOString() };
}
export function preciseRange(start: string, end: string): TimeRange {
  const a = new Date(`${start}+09:00`),
    b = new Date(`${end}+09:00`);
  if (!Number.isFinite(+a) || !Number.isFinite(+b) || +a >= +b)
    throw new Error('종료 시각은 시작 시각보다 늦어야 합니다.');
  return { start: a.toISOString(), end: b.toISOString() };
}
export const escapeHtml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
export const csvCell = (value: string | number | null) => {
  if (typeof value === 'number') return String(value);
  let s = value == null ? '근거 부족' : value;
  if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
  return `"${s.replace(/"/g, '""')}"`;
};
export const incidentTransitions: Record<string, string[]> = {
  open: ['investigating'],
  investigating: ['resolved', 'open'],
  resolved: ['closed', 'investigating'],
  closed: ['investigating'],
};
export function nextSchedule(
  frequency: string,
  localTime: string,
  weekday: number,
  day: number,
  now = new Date(),
) {
  const local = new Date(now.getTime() + 9 * 3600000);
  const [h, m] = localTime.split(':').map(Number);
  const candidate = new Date(
    Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate(), h, m),
  );
  if (frequency === 'weekly') {
    candidate.setUTCDate(candidate.getUTCDate() + ((weekday - candidate.getUTCDay() + 7) % 7));
    if (+candidate <= +local) candidate.setUTCDate(candidate.getUTCDate() + 7);
  } else if (frequency === 'monthly') {
    const setDay = () =>
      candidate.setUTCDate(
        Math.min(
          day,
          new Date(
            Date.UTC(candidate.getUTCFullYear(), candidate.getUTCMonth() + 1, 0),
          ).getUTCDate(),
        ),
      );
    candidate.setUTCDate(1);
    setDay();
    if (+candidate <= +local) {
      candidate.setUTCDate(1);
      candidate.setUTCMonth(candidate.getUTCMonth() + 1);
      setDay();
    }
  } else if (+candidate <= +local) candidate.setUTCDate(candidate.getUTCDate() + 1);
  return new Date(candidate.getTime() - 9 * 3600000).toISOString();
}
