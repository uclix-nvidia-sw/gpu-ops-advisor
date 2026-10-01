import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { topics, topicId } from '../lib/live';
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
const render = (path = '/operator-guide') =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Shell />}>
          <Route path="operator-guide" element={<OperatorGuide />} />
          <Route path="reports" element={<p>report-content-marker</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

it.each(['classic', 'operations', 'developer'])(
  'keeps all topic guidance accessible while disconnected in %s mode',
  (mode) => {
    app.mode = mode;
    app.connection.isError = true;
    const html = render();
    for (const [i, name] of topics.entries()) {
      expect(html).toContain(`<strong>${name}</strong>`);
      expect(html).toContain(`>${topicId(i)}</span>`);
    }
    expect(html).toContain('href="/operator-guide"');
    expect(html).toContain('href="/reports/new"');
    expect(html).toContain('실시간 연결 상태나 데이터 보유 여부를 판정하는 화면은 아닙니다');
    expect(html).toContain('전체 커버리지는 분모 부족으로 산출하지 않습니다');
    expect(html).toContain('발생률과 전체 정비 순위는 아직 산출하지 않습니다');
    expect(html).not.toContain('fixture offline');
    expect(html).not.toContain('class="scopebar"');
  },
);
it('allows reading before cluster registration without opening report execution', () => {
  app.mode = 'classic';
  app.connection.isError = false;
  expect(render()).toContain('분석 주제 11개');
  expect(render('/reports')).toContain('등록된 클러스터가 없습니다');
  expect(render('/reports')).not.toContain('report-content-marker');
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
