import { expect, it } from 'vitest';
import {
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
