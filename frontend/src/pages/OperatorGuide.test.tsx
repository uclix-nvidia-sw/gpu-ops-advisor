import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { reportKinds } from '../lib/reportKinds';
import { OperatorGuide } from './OperatorGuide';

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
it('allows reading before cluster registration without opening report execution', () => {
  app.mode = 'classic';
  app.connection.isError = false;
  expect(render()).toContain('11개 소주제');
  expect(render('/reports')).toContain('등록된 클러스터가 없습니다');
  expect(render('/reports')).not.toContain('report-content-marker');
  expect(render('/reports')).toContain('href="/operator-guide"');
});

it.each(['start', 'topics', 'values', 'missing', 'unknown'])(
  'shows only the selected guide section for %s',
  (key) => {
    const html = render(`/operator-guide#guide-${key}`);
    const selected = key === 'unknown' ? 'start' : key;
    for (const section of ['start', 'topics', 'values', 'missing']) {
      expect(html.includes(`<section id="guide-${section}" hidden=""`)).toBe(section !== selected);
      expect(html).toContain(
        `aria-pressed="${section === selected}" aria-controls="guide-${section}"`,
      );
    }
    expect(render()).not.toContain('<section id="guide-start" hidden=""');
  },
);

it('uses the saved report scope and keeps global controls on new requests', () => {
  const saved = render('/reports/saved');
  expect(saved).toContain('이 보고서의 분석 범위');
  expect(saved).toContain('saved-cluster');
  expect(saved).toContain('training');
  expect(saved).not.toContain('aria-label="조회 기간"');
  expect(saved).not.toContain('class="scope-button"');
  expect(render('/reports/new')).toContain('class="scope-button"');
});

it('hides the unused time selector on job history and detail while retaining scope and refresh', () => {
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
