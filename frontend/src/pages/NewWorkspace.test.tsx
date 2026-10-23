import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { NewWorkspace, summaryState } from './NewWorkspace';
import { ViewMode } from '../components/ViewMode';
import { RcaNarrative } from '../components/RcaNarrative';
import { ReportStatements } from '../components/ReportContent';
import type { Row } from '../lib/live';
const data = vi.hoisted(() => ({
  paths: [] as string[],
  incident: {} as Row,
  job: {} as Row,
  error: false,
  items: [] as Row[],
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({
    mode: 'new',
    ready: true,
    canOperate: true,
    scope: { clusters: [{ cluster_id: 'c1', namespaces: null }] },
    registeredScope: { clusters: [{ cluster_id: 'c1', namespaces: null }] },
    timeRange: { start: '2026-10-01T00:00:00Z', end: '2026-10-02T00:00:00Z' },
  }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: (path: string) => {
    data.paths.push(path);
    return {
      data: path.startsWith('/incidents/') ? data.incident : data.job,
      isPending: false,
      isError: data.error,
      error: new Error('연결 실패'),
    };
  },
  useList: (path: string | null) => {
    if (path) data.paths.push(path);
    return {
      items: path?.startsWith('/incidents?') ? data.items : [],
      isPending: false,
      isError: data.error,
      error: new Error('연결 실패'),
    };
  },
  useCommand: () => ({ run: vi.fn(), error: '', busy: false }),
}));
const render = (route: string) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[route]}>
      <NewWorkspace />
    </MemoryRouter>,
  );
beforeEach(() => {
  data.paths = [];
  data.error = false;
  data.items = [];
  data.incident = {
    id: 'i1',
    scope: { clusters: [{ cluster_id: 'stored-cluster', namespaces: ['training'] }] },
    review_status: 'unreviewed',
    symptom: 'GPU 오류',
    rca_summary: {
      latest_job: { job_id: 'new', status: 'running' },
      latest_published: { job_id: 'published', result_ref: 'candidate' },
    },
  };
  data.job = {
    id: 'published',
    incident_id: 'i1',
    scope: { clusters: [{ cluster_id: 'stored-cluster', namespaces: ['training'] }] },
    status: 'succeeded',
    result_ref: 'candidate',
    result: {
      result_status: 'partial',
      narrative: [
        { id: 'problem', title: '확인한 사실', text: '메모리 오류가 보고되었습니다.' },
        { id: 'limits', title: '남은 제한', text: '원인 미확정' },
      ],
      raw_debug: 'SECRET',
      quality: { report: { presentation: 'incident-first/2' } },
    },
  };
});
it('retains four comparison modes and appends two consoles', () => {
  const html = renderToStaticMarkup(<ViewMode />);
  expect(html.match(/<button/g)).toHaveLength(6);
  expect(html.indexOf('신규')).toBeLessThan(html.indexOf('개발 콘솔'));
  expect(html.indexOf('개발 콘솔')).toBeLessThan(html.indexOf('운영 콘솔'));
  expect(html.indexOf('기존')).toBeLessThan(html.indexOf('운영'));
  expect(html).toContain('개발자');
  expect(html).toContain('신규');
});
it('distinguishes absent compatibility field from no investigation', () => {
  expect(summaryState({})).toBe('분석 요약 미확인');
  expect(summaryState({ rca_summary: { latest_job: null, latest_published: null } })).toBe(
    '조사 기록 없음',
  );
});
it('uses the publication summary while the latest investigation runs', () => {
  const html = render('/incidents/i1');
  expect(data.paths).toContain('/analyses/published');
  expect(data.paths).not.toContain('/analyses/new');
  expect(html).toContain('메모리 오류가 보고되었습니다.');
  expect(html).toContain('실행 중');
  expect(html).toContain('남은 제한');
  expect(html).not.toContain('SECRET');
  expect(data.paths.some((p) => /evidence|trace|attempts/.test(p))).toBe(false);
});
it('never reads a candidate without a publication', () => {
  data.incident.rca_summary = {
    latest_job: { job_id: 'private', status: 'succeeded' },
    latest_published: null,
  };
  const html = render('/incidents/i1');
  expect(html).toContain('공개된 분석 결과가 없습니다');
  expect(data.paths).not.toContain('/analyses/private');
});
it('opens the requested historical RCA inside its incident and keeps records incident-scoped', () => {
  data.job.id = 'older-published';
  const html = render('/incidents/i1?analysis=older-published');
  expect(data.paths).toContain('/analyses/older-published');
  expect(data.paths).not.toContain('/analyses/published');
  expect(html).toContain('지정한 조사 결과');
  expect(html).toContain('사건 검토·조치 기록');
  expect(html).toContain('기록을 저장해도 아래 상태는 바뀌지 않습니다');
  expect(html.match(/<form/g)).toHaveLength(1);
  expect(data.paths).toContain('/reviews?subject_type=incident&subject_id=i1&limit=30');
  expect(data.paths).toContain('/reviews?subject_type=job&subject_id=older-published&limit=30');
});
it('rejects an analysis URL belonging to another incident', () => {
  data.job.incident_id = 'different-incident';
  const html = render('/incidents/i1?analysis=other-job');
  expect(html).toContain('선택한 분석과 이 사건의 연결을 확인할 수 없습니다');
  expect(html).not.toContain('메모리 오류가 보고되었습니다.');
  expect(data.paths.some((p) => p.includes('subject_id=other-job'))).toBe(false);
});
it('routes standalone RCA review to its original incident and preserves old job records read-only', () => {
  const html = render('/analyses/published');
  expect(html).toContain('/incidents/i1?analysis=published#new-review-records');
  expect(html).toContain('분석별 이전 기록 보기');
  expect(html).toContain('stored-cluster');
  expect(html).not.toContain('<form');
  expect(html).not.toContain('정정 기록 작성');
  expect(data.paths).toContain('/reviews?subject_type=job&subject_id=published&limit=30');
});
it('lists incidents without per-row analysis calls', () => {
  data.items = [data.incident, { ...data.incident, id: 'i2' }];
  const html = render('/cases?status=open');
  expect(html).toContain('GPU 오류');
  expect(data.paths.filter((p) => p.startsWith('/analyses'))).toHaveLength(0);
  expect(data.paths[0]).toContain('status=open');
  expect(html).toContain('최근 접수순');
});
it('shows API failure without healthy or empty success', () => {
  data.error = true;
  const html = render('/cases');
  expect(html).toContain('연결 실패');
  expect(html).not.toContain('조건에 맞는 사건이 없습니다');
});
it('marks no events as missing rather than healthy', () => {
  const html = render('/analyses/published');
  expect(html).toContain('오류가 없다는 의미는 아닙니다');
});
it('keeps unpublished reports in the new reader', () => {
  data.job = { id: 'r1', kind: 'report', status: 'failed', result_ref: null };
  const html = render('/reports/r1');
  expect(html).toContain('실행 실패');
  expect(html).not.toContain('HTML');
  expect(html).not.toContain('/jobs/');
});
it('uses the shared aggregate reader styles and shows its analysis period once with interpretation and limits intact', () => {
  data.job = {
    id: 'report-aggregate',
    kind: 'report',
    status: 'succeeded',
    result_ref: 'published',
    scope: { clusters: [{ cluster_id: 'saved-cluster', namespaces: ['training'] }] },
    result: {
      result_status: 'partial',
      narrative_status: 'complete',
      time_range: { start: '2026-10-20T15:00:00Z', end: '2026-10-21T15:00:00Z' },
      quality: { report_format: 'report-aggregate-v1', report: { method: 'llm_interpreted' } },
      topics: [
        {
          topic_id: 'namespace_usage',
          findings: [{ id: 'saved-fact', text: '저장된 계산 근거' }],
          rows: [],
        },
      ],
      narrative: [
        {
          topic_id: 'namespace_usage',
          observation: '저장된 활동 변화',
          meaning: '관측 범위에서 해석',
          next_check: '기록 대조',
          interpretation_limit: '일부 시간대 미관측',
          source_fact_ids: ['saved-fact'],
        },
      ],
    },
  };
  const html = render('/reports/report-aggregate');
  expect(html).toContain('id="new-report-document" class="report-workspace new-report-document"');
  expect(html.match(/class="report-period"/g)).toHaveLength(1);
  expect(html).toContain('class="report-workspace new-report-body"');
  expect(html).toContain('saved-cluster');
  expect(html).toContain('직전 같은 길이의 기간과 비교');
  expect(html).toContain('저장된 활동 변화');
  expect(html).toContain('일부 시간대 미관측');
  expect(html).toContain('저장된 계산 근거');
  expect(html).toContain('해석 근거와 계산 결과');
});
it('uses an explicit developer switch on direct diagnostic routes', () => {
  for (const path of ['/jobs', '/knowledge', '/settings/models', '/fleet/assets'])
    expect(render(path)).toContain('개발자 화면으로 전환');
});
it('removes opaque target paragraphs and diagnostics only from the new narrative', () => {
  const result = {
    narrative: [
      { id: 'problem', text: '대상 식별 정보: SECRET-ID' },
      { id: 'limits', title: '판단 제한', text: '판단 보류' },
    ],
  };
  const old = renderToStaticMarkup(<RcaNarrative result={result} />);
  const reader = renderToStaticMarkup(<RcaNarrative result={result} reader />);
  expect(old).toContain('SECRET-ID');
  expect(reader).not.toContain('SECRET-ID');
  expect(reader).toContain('판단 보류');
});

it('retains withheld advice, conditions and missing values without raw records', () => {
  data.job = {
    id: 'r1',
    kind: 'report',
    status: 'succeeded',
    result_ref: 'public',
    result: {
      result_status: 'blocked',
      narrative_status: 'failed',
      topics: [
        {
          topic_id: 'O03',
          status: 'blocked',
          metrics: [
            {
              id: 'O03.low_gpu_hours',
              value: null,
              unit: 'hours',
              quality: { reason: 'required_data_missing' },
            },
          ],
          recommendations: [
            {
              text: '작업 목적을 확인하세요',
              eligibility: 'withheld',
              execution: 'not_performed',
              reason: 'workload_purpose_unverified',
              preconditions: ['workload_exception_review'],
              evidence_refs: ['SECRET-REF'],
            },
          ],
        },
      ],
    },
  };
  const html = render('/reports/r1');
  expect(html).toContain('권고 보류');
  expect(html).toContain('조치 미수행');
  expect(html).toContain('산출 불가');
  expect(html).toContain('체크포인트');
  expect(html).not.toContain('SECRET-REF');
  expect(html).not.toContain('상세 기록');
});

it('keeps legacy creation links explicit instead of silently changing their topics', () => {
  expect(render('/reports/new?legacy=true')).toContain('개발자 화면으로 전환');
  expect(render('/reports/new?kind=health')).not.toContain('보고서 생성 요청');
});
it('retains historical RCA facts when a narrative is absent', () => {
  data.job.result = {
    result_status: 'partial',
    facts: [{ text: '과거 관측 사실' }],
    cause_candidates: [{ text: '확인 중인 후보' }],
    recommendations: [],
    missing_inputs: ['device_identity_unverified'],
  };
  const html = render('/analyses/published');
  expect(html).toContain('과거 관측 사실');
  expect(html).toContain('원인 후보 · 확정 아님');
  expect(html).toContain('충족되지 않은 판단 조건');
});

it('names list destinations and keeps report navigation available in detail and creation screens', () => {
  const home = render('/dashboard');
  expect(home).toMatch(/href="\/cases"[^>]*>사건 목록 보기/);
  expect(home).toMatch(/href="\/reports"[^>]*>보고서 목록 보기/);
  for (const route of [
    '/reports',
    '/reports/r1',
    '/reports/new',
    '/reports/new?schedule=true',
    '/schedules',
    '/schedules/s1',
    '/operator-guide',
  ]) {
    const html = render(route);
    expect(html).toContain('aria-label="운영 보고서 메뉴"');
    expect(html).toMatch(/href="\/schedules"[^>]*>자동 보고서 설정/);
    expect(html).toMatch(/href="\/reports"[^>]*>보고서 목록/);
  }
});
it('names the actual return destination and preserves filters while rejecting outside paths', () => {
  for (const [from, href, name] of [
    ['/dashboard', '/dashboard', '운영 현황'],
    ['/cases?status=open', '/cases?status=open', '사건 목록'],
    ['/reports/r1', '/reports/r1', '보고서 상세'],
    ['https://example.com', '/cases', '사건 목록'],
  ]) {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={[{ pathname: '/incidents/i1', state: { from } }]}>
        <NewWorkspace />
      </MemoryRouter>,
    );
    expect(html).toContain(`href="${href}"`);
    expect(html).toContain(name);
    expect(html).not.toContain('이전 화면');
  }
});
it('distinguishes schedule creation and its return destination from a one-time report', () => {
  const scheduled = render('/reports/new?schedule=true');
  expect(scheduled).toContain('자동 보고서 일정 추가');
  expect(scheduled).toMatch(/aria-current="location" href="\/schedules"/);
  expect(scheduled).toMatch(/href="\/schedules"[^>]*>자동 보고서 설정 목록으로/);
  const manual = render('/reports/new');
  expect(manual).toContain('보고서 요청');
  expect(manual).toMatch(/href="\/reports"[^>]*>보고서 목록으로/);
});

it('exposes incident actions before the long report and links to real sections', () => {
  const html = render('/incidents/i1');
  expect(html.indexOf('사건 상세 바로가기')).toBeLessThan(
    html.indexOf('메모리 오류가 보고되었습니다.'),
  );
  for (const id of [
    'new-analysis-result',
    'new-investigation-history',
    'new-incident-state',
    'new-review-records',
  ]) {
    expect(html).toContain(`href="#${id}"`);
    expect(html).toContain(`id="${id}"`);
  }
  expect(html).toContain('저장하려면 입력하세요: 내용');
  expect(html).toContain('aria-describedby="new-review-save-help"');
});
it('offers report creation directly from the home screen', () => {
  expect(render('/dashboard')).toMatch(/href="\/reports\/new"[^>]*>보고서 만들기/);
});

it('preserves existing report sections and diagnostic controls when evidence is connected', () => {
  const empty = renderToStaticMarkup(
    <ReportStatements title="기존 권고" items={[]} metrics={[]} onEvidence={() => {}} />,
  );
  expect(empty).toContain('기존 권고');
  const old = renderToStaticMarkup(
    <ReportStatements
      title="기존 권고"
      items={[{ text: '기존 내용', evidence_refs: ['e1'] }]}
      metrics={[]}
      onEvidence={() => {}}
    />,
  );
  expect(old).toContain('관련 근거');
  expect(old).toContain('상세 기록');
  expect(renderToStaticMarkup(<ReportStatements title="신규 권고" items={[]} metrics={[]} />)).toBe(
    '',
  );
});
