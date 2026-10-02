import { expect, it } from 'vitest';
import {
  reportPeriodLabel,
  reportRequestTime,
  previousReportDay,
  reportDayRange,
  reportDaySummary,
  schedulePeriods,
} from './reportPeriod';
it('uses inclusive KST days across month boundaries', () => {
  expect(previousReportDay(new Date('2026-10-01T00:00:00Z'))).toBe('2026-09-30');
  expect(reportDayRange('2026-09-30', '2026-09-30')).toEqual({
    start: '2026-09-29T15:00:00.000Z',
    end: '2026-09-30T15:00:00.000Z',
  });
  expect(reportDaySummary('2026-09-28', '2026-10-04')).toContain('7일');
  expect(Object.keys(schedulePeriods)).toEqual(['daily', 'weekly', 'monthly']);
});
it('rejects hours, invalid dates, reversed dates and more than 31 days', () => {
  for (const [start, end] of [
    ['2026-01-01T12:00', '2026-01-02'],
    ['2026-02-29', '2026-03-01'],
    ['2026-10-02', '2026-10-01'],
    ['2024-01-01', '2025-01-01'],
    ['', ''],
  ]) {
    expect(() => reportDayRange(start, end)).toThrow();
  }
});

it('labels full KST days without including the exclusive end date', () => {
  expect(reportPeriodLabel('2026-09-30T15:00:00Z', '2026-10-01T15:00:00Z')).toBe(
    '2026. 10. 01. 하루 · 1일(24시간)',
  );
  expect(reportPeriodLabel('2026-09-30T15:00:00Z', '2026-10-07T15:00:00Z')).toBe(
    '2026. 10. 01. ~ 2026. 10. 07. 포함 · 7일(168시간)',
  );
  expect(reportPeriodLabel('2026-12-31T15:00:00Z', '2027-01-01T15:00:00Z')).toContain(
    '2027. 01. 01. 하루',
  );
});
it('keeps older hourly and non-midnight 24-hour ranges exact', () => {
  expect(reportPeriodLabel('2026-10-01T03:00:00Z', '2026-10-01T05:00:00Z')).toBe(
    '2026. 10. 01. 12:00:00 – 2026. 10. 01. 14:00:00 · 2시간',
  );
  const legacy = reportPeriodLabel('2026-09-30T02:06:00Z', '2026-10-01T02:06:00Z');
  expect(legacy).toContain('11:06:00');
  expect(legacy).not.toContain('하루');
  expect(reportPeriodLabel('', '')).toContain('미확인');
  expect(reportPeriodLabel('2026-10-02', '2026-10-01')).toContain('미확인');
});
it('shows request receipt seconds in KST without confusing it with the analyzed date', () => {
  expect(reportRequestTime('2026-10-02T02:37:18.885847+00:00')).toBe('2026. 10. 02. 11:37:18');
  expect(reportRequestTime('')).toBe('미확인');
});
