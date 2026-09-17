import { describe, expect, it } from 'vitest';
import { allScope, initialDatabase, timeRange } from '../data/fixtures';
import { calendarRange, csvCell, escapeHtml, inScope, nextSchedule, preciseRange } from './domain';
import { advanceJobs, createJob } from './jobs';
describe('calendar and observation boundaries', () => {
  it('allows a same-day report and uses an exclusive next-day KST boundary', () => {
    expect(calendarRange('2026-09-16', '2026-09-16')).toEqual({
      start: '2026-09-15T15:00:00.000Z',
      end: '2026-09-16T15:00:00.000Z',
    });
  });
  it('rejects reversed and empty time ranges', () => {
    expect(() => calendarRange('2026-09-17', '2026-09-15')).toThrow();
    expect(() => preciseRange('2026-09-16T12:00', '2026-09-16T12:00')).toThrow();
  });
  it('keeps CPC/namespace grants paired', () => {
    const scope = {
      clusters: [
        { cluster_id: 'cpc-1', namespaces: ['dev'] },
        { cluster_id: 'cpc-2', namespaces: ['prod'] },
      ],
    };
    expect(inScope(scope, 'cpc-1', 'prod')).toBe(false);
    expect(inScope(scope, 'cpc-2', 'prod')).toBe(true);
  });
  it('clamps missing monthly dates to month end', () => {
    expect(nextSchedule('monthly', '09:00', 1, 31, new Date('2026-02-02T00:00:00Z'))).toBe(
      '2026-02-28T00:00:00.000Z',
    );
  });
  it('moves a past weekly slot to the following week', () => {
    expect(nextSchedule('weekly', '09:00', 1, 1, new Date('2026-09-14T01:00:00Z'))).toBe(
      '2026-09-21T00:00:00.000Z',
    );
  });
});
describe('safe demo export', () => {
  it('neutralizes spreadsheet formulas in text while preserving numeric negatives', () => {
    expect(csvCell('=HYPERLINK("bad")')).toBe('"\'=HYPERLINK(""bad"")"');
    expect(csvCell(-10)).toBe('-10');
    expect(csvCell(null)).toBe('"근거 부족"');
  });
  it('escapes HTML from user text', () => {
    expect(escapeHtml('<script>alert("x")</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    );
  });
});
describe('demo job lifecycle', () => {
  it('completes execution with blocked results when there is no observational input', () => {
    const db = structuredClone(initialDatabase);
    const job = createJob({ kind: 'rca', title: 'test', scope: allScope, time_range: timeRange });
    db.jobs = [job];
    advanceJobs(db, Date.parse(job.created_at) + 7000);
    expect(job.status).toBe('succeeded');
    expect(job.result_status).toBe('blocked');
    expect(job.narrative_status).toBe('omitted');
  });
  it('confirms cancellation separately from the request', () => {
    const db = structuredClone(initialDatabase);
    const job = createJob({
      kind: 'report',
      title: 'test',
      scope: allScope,
      time_range: timeRange,
    });
    job.cancel_requested_at = new Date().toISOString();
    db.jobs = [job];
    expect(job.status).toBe('queued');
    advanceJobs(db);
    expect(job.status).toBe('cancelled');
    expect(job.result_status).toBeNull();
  });
  it('expires an active job without inventing a result', () => {
    const db = structuredClone(initialDatabase);
    const job = createJob({ kind: 'rca', title: 'test', scope: allScope, time_range: timeRange });
    db.jobs = [job];
    advanceJobs(db, Date.parse(job.deadline_at) + 1);
    expect(job.status).toBe('expired');
    expect(job.result_status).toBeNull();
  });
  it('does not revise terminal jobs', () => {
    const db = structuredClone(initialDatabase);
    const before = structuredClone(db.jobs);
    advanceJobs(db, Date.now() + 86400000);
    expect(db.jobs).toEqual(before);
  });
});
