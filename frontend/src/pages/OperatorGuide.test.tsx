import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { reportKinds } from '../lib/reportKinds';
import { OperatorGuide } from './OperatorGuide';
import { advicePresentation } from '../lib/namespaceAdvice';

const app = vi.hoisted(() => ({
  mode: 'classic',
  ready: false,
  connection: { isPending: false, isError: true, error: new Error('fixture offline') },
  scope: { clusters: [] },
  registeredScope: { clusters: [] },
  period: '1h',
}));
vi.mock('../lib/store', () => ({ useApp: () => app }));
const render = (path = '/operator-guide') => {
  const client = new QueryClient();
  client.setQueryData(['api', '/reports/saved', undefined], {
    result: { scope: { clusters: [{ cluster_id: 'saved-cluster', namespaces: ['training'] }] } },
  });
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Shell />}>
            <Route path="operator-guide" element={<OperatorGuide />} />
            <Route path="jobs" element={<p>jobs-content-marker</p>} />
            <Route path="jobs/:id" element={<p>job-detail-marker</p>} />
            <Route path="reports" element={<p>report-content-marker</p>} />
            <Route path="reports/:id" element={<p>report-detail-marker</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

it.each(['classic', 'operations', 'developer'])(
  'keeps all topic guidance accessible while disconnected in %s mode',
  (mode) => {
    app.mode = mode;
    app.connection.isError = true;
    const html = render();
    for (const kind of reportKinds) {
      const label = kind.id === 'health' ? 'GPU 상태·에너지·장애' : kind.name;
      expect(html).toContain(`<strong>${label}</strong>`);
    }
    expect(html).toContain('id="guide-kind-content"');
    expect(html).toContain('>O08</span>');
    expect(html).not.toContain('>O01</span>');
    expect(html).toContain('href="/reports/new?kind=namespace"');
    const sidebar = html.match(/<nav class="main-nav"[^>]*>(.*?)<\/nav>/s)?.[1];
    expect(sidebar).toBeDefined();
    expect(sidebar).not.toContain('href="/operator-guide"');
    expect(sidebar).toMatch(/class="nav-item active" aria-current="page" href="\/reports"/);
    expect(html).toMatch(/class="active" aria-current="page" href="\/operator-guide"/);
    expect(html).toContain('href="/schedules"');
    expect(html).toContain('href="/reports/new"');
    expect(html).toContain('실시간 연결 상태나 데이터 보유 여부를 판정하는 화면은 아닙니다');
    expect(html).not.toContain('fixture offline');
    expect(html).not.toContain('class="scopebar"');
  },
);
it.each(['classic', 'operations'])(
  'allows reading before cluster registration without opening report execution in %s',
  (mode) => {
    app.mode = mode;
    app.connection.isError = false;
    expect(render()).toContain('일일 운영 보고서로 시작하세요');
    expect(render()).not.toContain('11개 소주제를 담습니다');
    expect(render('/reports')).toContain('등록된 클러스터가 없습니다');
    expect(render('/reports')).not.toContain('report-content-marker');
    expect(render('/reports')).toContain('href="/operator-guide"');
  },
);

it.each(['start', 'topics', 'advice', 'values', 'missing', 'legacy', 'unknown'])(
  'shows only the selected guide section for %s',
  (key) => {
    const html = render(`/operator-guide#guide-${key}`);
    const selected = key === 'unknown' ? 'start' : key;
    for (const section of ['start', 'topics', 'advice', 'values', 'missing', 'legacy']) {
      expect(html.includes(`<section id="guide-${section}" hidden=""`)).toBe(section !== selected);
      expect(html).toContain(
        `aria-pressed="${section === selected}" aria-controls="guide-${section}"`,
      );
    }
    expect(render()).not.toContain('<section id="guide-start" hidden=""');
  },
);

// The developer comparison keeps the global bar; console2 renders saved scope inside the report.
it('uses the saved report scope and keeps global controls on new requests', () => {
  app.mode = 'developer';
  const saved = render('/reports/saved');
  expect(saved).toContain('이 보고서의 분석 범위');
  expect(saved).toContain('saved-cluster');
  expect(saved).toContain('training');
  expect(saved).not.toContain('aria-label="조회 기간"');
  expect(saved).not.toContain('class="scope-button"');
  expect(render('/reports/new')).toContain('class="scope-button"');
});

it('hides the unused time selector on job history and detail while retaining scope and refresh', () => {
  app.mode = 'operations';
  const html = render('/jobs');
  expect(html).not.toContain('aria-label="조회 기간"');
  expect(html).toContain('class="scope-button"');
  expect(html).toContain('aria-label="데이터 새로고침"');
  expect(render('/jobs/saved')).not.toContain('aria-label="조회 기간"');
  expect(render('/reports/new')).not.toContain('aria-label="조회 기간"');
  expect(render('/reports')).not.toContain('aria-label="조회 기간"');
});

it('keeps a guide entry on reports when the connection fails', () => {
  app.connection.isError = true;
  const html = render('/reports');
  expect(html).toContain('href="/operator-guide"');
  expect(html).toContain('fixture offline');
  expect(html).not.toContain('report-content-marker');
});

it('explains current aggregate advice order, time windows, AI fallback and all seven types', () => {
  app.mode = 'classic';
  const html = render('/operator-guide#guide-values');
  for (const text of [
    '클러스터·네임스페이스 이름순이며',
    '저장된 순서',
    '실패한 주제는 계산 요약을 표시합니다',
    '표본 수로 나눈',
    'KST이며 끝 시각은 포함하지 않습니다',
    '대기 작업에 GPU를 더 할당할지 검토',
    '작업 시작 시간을 바꿔볼지 검토',
    '작업 시작 시간을 나눠볼지 검토',
    '작업이 시작되지 못한 단계 점검',
    '완료 기록을 다음 작업 계획에 참고할지 검토',
    '새 작업 배치 전 GPU 메모리 점유 확인',
    '여러 시간대에 나타난 작업 대기 원인 점검',
  ])
    expect(html).toContain(text);
  expect(html).not.toContain('AI는 검증된 문장의 우선순위를 정합니다');
  expect(html).not.toContain('Namespace 비교표에서 대상을 선택하세요');
});

it('separates current report topics from preserved legacy request guidance', () => {
  const html = render('/operator-guide#guide-topics');
  const current = html.match(
    /<section id="guide-topics"[^>]*>(.*?)<section id="guide-advice"/s,
  )?.[1];
  expect(current).toContain('Namespace별 GPU 활동 현황');
  expect(current).toContain('기간 내 장애 알림 현황');
  expect(current).not.toContain('guide-kind-picker');
  expect(current).not.toContain('/reports/new?kind=');
  expect(html).toContain('<section id="guide-legacy" hidden=""');
  const legacy = render('/operator-guide#guide-legacy');
  expect(legacy).not.toContain('<section id="guide-legacy" hidden=""');
  expect(legacy).toContain('href="/reports/new?kind=namespace"');
});

it('reuses the report headings and general bases without presenting them as new AI observations', () => {
  const html = render('/operator-guide#guide-advice');
  const advice =
    html.match(/<section id="guide-advice"[^>]*>(.*?)<section id="guide-values"/s)?.[1] || '';
  for (const kind of [
    'capacity_review',
    'repeated_activity',
    'schedule_candidate',
    'relative_activity',
    'queue_review',
    'resident_memory',
    'batch_progress',
  ]) {
    const presentation = advicePresentation({ kind });
    expect(advice).toContain(presentation.title);
    expect(advice).toContain(presentation.basis);
  }
  expect(advice).toContain('실제 관측은 보고서 본문과 근거에서 확인하세요');
  expect(advice).toContain('다른 네임스페이스로 옮기는 제안이 아닙니다');
  expect(html).toContain('과거 보고서는 생성 당시 기준을 따릅니다');
  expect(html).not.toContain('서버 HTML 다운로드도 같은 정렬');
});
