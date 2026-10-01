import type { TimeRange } from './types';

export const schedulePeriods: Record<string, string> = {
  daily: 'previous_complete_day',
  weekly: 'previous_complete_week',
  monthly: 'previous_complete_month',
};
export const scheduleLabels: Record<string, string> = {
  daily: '일간 (매일)',
  weekly: '주간 (매주)',
  monthly: '월간 (매월)',
};
export const scheduleWindows: Record<string, string> = {
  daily: '직전 완료된 하루',
  weekly: '직전 완료된 한 주',
  monthly: '직전 완료된 한 달',
};
const dayMs = 86400000;
export const previousReportDay = (now = new Date()) =>
  new Date(+now + 9 * 3600000 - dayMs).toISOString().slice(0, 10);
// The inclusive date selection becomes the existing half-open absolute range in KST.
export function reportDayRange(first: string, last: string): TimeRange {
  const date = (value: string) => {
    const utc = new Date(`${value}T00:00:00Z`);
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      !Number.isFinite(+utc) ||
      utc.toISOString().slice(0, 10) !== value
    )
      throw new Error('올바른 분석 날짜를 선택해 주세요.');
    return +utc - 9 * 3600000;
  };
  const start = date(first),
    end = date(last) + dayMs;
  if (end <= start) throw new Error('종료일은 시작일과 같거나 이후여야 합니다.');
  if (end - start > 31 * dayMs) throw new Error('분석 기간은 최대 31일입니다.');
  return { start: new Date(start).toISOString(), end: new Date(end).toISOString() };
}
export function reportDaySummary(first: string, last: string) {
  try {
    const range = reportDayRange(first, last);
    return `${first} ~ ${last} 포함 · ${(Date.parse(range.end) - Date.parse(range.start)) / dayMs}일 · 시작일 00:00부터 종료일 다음 날 00:00까지`;
  } catch (error) {
    return (error as Error).message;
  }
}
