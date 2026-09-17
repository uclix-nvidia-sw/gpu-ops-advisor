import type { Database, Job, Scope, TimeRange } from './types';
export function createJob(input: {
  kind: 'rca' | 'report';
  title: string;
  scope: Scope;
  time_range: TimeRange;
  target?: string;
  topic_ids?: string[];
  purpose_ids?: string[];
  parent_job_id?: string;
  incident_id?: string;
  request?: Record<string, unknown>;
}): Job {
  const now = new Date();
  return {
    ...input,
    request: input.request || {},
    id: crypto.randomUUID(),
    status: 'queued',
    stage: '접수 대기',
    result_status: null,
    narrative_status: null,
    created_at: now.toISOString(),
    deadline_at: new Date(+now + 3600000).toISOString(),
    attempt_no: 1,
    version: 1,
    can_cancel: true,
    can_retry: false,
  };
}
/** Demo-only lifecycle; backend will own transitions and persistent results in production. */
export function advanceJobs(db: Database, now = Date.now()) {
  for (const job of db.jobs) {
    if (!['queued', 'running', 'retry_wait'].includes(job.status)) continue;
    if (job.cancel_requested_at) {
      job.status = 'cancelled';
      job.stage = '취소 확정';
      job.can_cancel = false;
      job.termination_reason = '운영자 취소 요청';
      job.version++;
      continue;
    }
    if (now >= Date.parse(job.deadline_at)) {
      job.status = 'expired';
      job.can_cancel = false;
      job.stage = '기한 만료';
      job.version++;
      continue;
    }
    const elapsed = now - Date.parse(job.started_at || job.created_at);
    if (elapsed > 6000) {
      job.status = 'succeeded';
      job.stage = '결과 저장 완료';
      job.result_status = 'blocked';
      job.narrative_status = 'omitted';
      job.can_cancel = false;
      job.version++;
    } else if (elapsed > 1500) {
      job.status = 'running';
      job.stage = elapsed > 4000 ? '입력 충분성 확인' : '관측 조회';
      job.version++;
    }
  }
}
