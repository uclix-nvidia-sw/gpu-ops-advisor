import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { JobDebug } from './JobDebug';
import { RecordInspector } from './RecordInspector';
import {
  debugPath,
  evidenceRelation,
  jobRelation,
  knowledgeRelation,
  relationMismatch,
  returnPath,
  selectedAttempt,
} from '../lib/debug';
import type { Row } from '../lib/live';

const view = vi.hoisted(() => ({ mode: 'developer' }));
vi.mock('../lib/store', () => ({ useApp: () => ({ mode: view.mode, canOperate: true }) }));
const job = {
  id: 'job-1',
  kind: 'rca',
  status: 'succeeded',
  attempt_no: 2,
  incident_id: 'incident-1',
  result_ref: 'candidate-2',
  result: { result_status: 'partial', evidence_refs: ['evidence-2'] },
  attempts: [
    { attempt_no: 1, termination_reason: 'timeout' },
    { attempt_no: 2, stage: 'complete' },
  ],
};
function render(tab: string, value: Row = job, trace?: Row, attempt = '1') {
  const client = new QueryClient();
  if (trace) client.setQueryData(['api', '/jobs/job-1/trace', undefined], trace);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          `/jobs/job-1?tab=${tab}&attempt=${attempt}&from=%2Fjobs%3Fstatus%3Dfailed`,
        ]}
      >
        <JobDebug job={value} onAction={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe('developer job workspace', () => {
  it('shows immutable model and knowledge revisions before publication from the job trace', () => {
    const trace = {
      job_id: job.id,
      evidence_version: 7,
      versions: {
        model: { model_id: 'pinned-model', model_revision: 4 },
        knowledge: [{ knowledge_id: 'runbook', revision: 3, content_hash: 'hash' }],
        execution_profile_revision: 'pinned-profile',
      },
    };
    const html = render('input', { ...job, result_ref: null }, trace);
    expect(html).toContain('사건 revision 7');
    expect(html).toContain('모델 revision 4');
    expect(html).toContain('<details><summary>고정된 지식 후보 1건</summary>');
    expect(html).toContain('지식 1 · revision 3');
    expect(html).toContain('pinned-model');
    expect(html).toContain('pinned-profile');
    expect(jobRelation({ ...job, result_ref: null }, 'model', 1, trace).record).toEqual(
      trace.versions.model,
    );
    expect(jobRelation({ ...job, result_ref: null }, 'model', 1, trace).source).toContain(
      'jobs.versions.model',
    );
    expect(
      render('input', { ...job, result_ref: null }, { ...trace, job_id: 'other' }),
    ).not.toContain('pinned-model');
  });
  it('compares the selected attempt to the immediately preceding recorded attempt', () => {
    const html = render(
      'execution',
      {
        ...job,
        attempts: [
          { attempt_no: 1, stage: 'collect', termination_reason: 'source_timeout' },
          { attempt_no: 2, stage: 'synthesis', termination_reason: 'llm_http_error' },
        ],
      },
      undefined,
      '2',
    );
    expect(html).toContain('이전 시도 1');
    expect(html).toContain('선택한 시도 2');
    expect(html).toContain('source_timeout');
    expect(html).toContain('llm_http_error');
    expect(render('execution')).toContain('비교할 이전 시도 기록이 없습니다');
  });
  it('does not substitute attempt zero or the latest failure for an invalid selection', () => {
    expect(selectedAttempt(job, null)).toBe(2);
    expect(selectedAttempt(job, '1')).toBe(1);
    for (const invalid of ['', 'NaN', '1.5', '-1', '9007199254740992']) {
      expect(selectedAttempt(job, invalid)).toBeNull();
      const html = render(
        'evidence',
        { ...job, termination_reason: 'PRIVATE_FAILURE' },
        undefined,
        invalid,
      );
      expect(html).toContain('유효한 시도를 선택해야');
      expect(html).not.toContain('시도 0의 조회·판단 기록');
      expect(html).not.toContain('PRIVATE_FAILURE');
    }
  });
  it('explains the selected failure without borrowing a different attempt termination', () => {
    view.mode = 'workbench';
    try {
      const current = {
        ...job,
        termination_reason: 'timeout',
        attempts: [{ attempt_no: 1, status: 'succeeded' }],
      };
      expect(render('execution', current)).not.toContain('선택한 시도의 종료 사유');
      const failed = {
        ...current,
        attempts: [{ attempt_no: 1, termination_reason: 'llm_http_error' }],
      };
      expect(render('execution', failed)).toContain('모델 서버가 HTTP 오류를 반환했습니다.');
      expect(render('execution', failed)).toContain('/settings/models');
    } finally {
      view.mode = 'developer';
    }
  });
  it('keeps selected attempt and return filters when changing the detail section', () => {
    const html = render('execution');
    expect(html).toContain('timeout');
    expect(html).toContain('tab=evidence&amp;attempt=1&amp;from=%2Fjobs%3Fstatus%3Dfailed');
    expect(html).not.toContain('근거 불러오기');
  });
  it('carries the original list from navigation state into reloadable tab links', () => {
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter
          initialEntries={[{ pathname: '/jobs/job-1', state: { from: '/reports?topic=O08' } }]}
        >
          <JobDebug job={job} onAction={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(html).toContain('from=%2Freports%3Ftopic%3DO08&amp;tab=execution');
  });
  it('requires the pinned knowledge revision and content hash to match', () => {
    const pinned = { knowledge_id: 'runbook-1', revision: 2, content_hash: 'pinned-hash' };
    const relation = knowledgeRelation(pinned);
    expect(relation.path).toBe('/knowledge/runbook-1/revisions/2');
    expect(relationMismatch({ ...pinned, content_hash: 'other-hash' }, relation.expected)).toEqual([
      'content_hash',
    ]);
    expect(knowledgeRelation({ knowledge_id: 'runbook-1' }).path).toBeUndefined();
  });
  it('keeps evidence in its own section and never renders an unpublished candidate', () => {
    expect(render('evidence')).toContain('시도 1의 조회·판단 기록');
    expect(render('result')).not.toContain('시도 1의 조회·판단 기록');
    const html = render('result', {
      ...job,
      result_ref: null,
      result: { summary: 'PRIVATE_CANDIDATE', evidence_refs: ['PRIVATE_REF'] },
    });
    expect(html).toContain('아직 공개된 결과가 없습니다');
    expect(html).not.toMatch(/PRIVATE_CANDIDATE|PRIVATE_REF/);
  });
  it('explains composite keys without substituting the current incident revision', () => {
    const relation = jobRelation(job, 'snapshot');
    expect(relation.join).toContain('(incident_id, revision)');
    expect(relation.unavailable).toContain('대체하지 않습니다');
    expect(relation.path).toBeUndefined();
    expect(jobRelation(job, 'attempt', 1).record).toMatchObject({
      job_id: 'job-1',
      attempt_no: 1,
      termination_reason: 'timeout',
    });
    expect(jobRelation(job, 'result').source).toContain('jobs.published_result_id');
  });
  it('blocks an unrelated evidence record instead of displaying its contents', () => {
    const client = new QueryClient();
    client.setQueryData(['api', '/evidence/evidence-2', undefined], {
      id: 'evidence-2',
      job_id: 'other-job',
      attempt_no: 2,
      snapshot: 'WRONG_RECORD',
    });
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <RecordInspector relation={evidenceRelation(job, 'evidence-2')} onClose={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(html).toContain('연결 불일치');
    expect(html).not.toContain('WRONG_RECORD');
  });
  it('uses a single debug destination and rejects external return destinations', () => {
    expect(returnPath('https://example.com')).toBe('/jobs');
    expect(returnPath('//example.com')).toBe('/jobs');
    expect(returnPath('/jobs\\evil')).toBe('/jobs');
    expect(returnPath('/reports?topic=O08')).toBe('/reports?topic=O08');
    expect(debugPath('job-1', 'result', '/cases?tab=reports')).toBe(
      '/jobs/job-1?tab=result&from=%2Fcases%3Ftab%3Dreports',
    );
  });
});
