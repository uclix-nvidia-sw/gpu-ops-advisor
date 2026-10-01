import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { reportReturnPath } from '../lib/reportNavigation';
import { Schedules } from './Schedules';
import { Reports, ReportForm } from './Reports';
import { OperationsReports } from './Operations';

const publication = vi.hoisted(() => ({
  status: 'succeeded',
  result_ref: 'r1' as string | null | undefined,
}));
beforeEach(() => {
  vi.stubGlobal('location', { pathname: '/reports' });
  publication.status = 'succeeded';
  publication.result_ref = 'r1';
});
afterEach(() => vi.unstubAllGlobals());
const paths = vi.hoisted(() => [] as string[]);
vi.mock('../lib/store', () => ({
  useApp: () => ({
    ready: true,
    canOperate: true,
    scope: { clusters: [] },
    timeRange: { start: '2026-09-30T00:00:00Z', end: '2026-10-01T00:00:00Z' },
  }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useCommand: () => ({ run: vi.fn(), busy: false, error: '', setError: vi.fn() }),
  useList: (path: string) => {
    paths.push(path);
    return {
      items: [
        {
          id: 'published',
          kind: 'report',
          report_spec: {
            topic_ids: ['O08'],
            group_by: ['namespace'],
            scope: { clusters: [{ cluster_id: 'cpc-2', namespaces: ['training'] }] },
          },
          frequency: 'weekly',
          weekday: 1,
          local_time: '09:00',
          timezone: 'Asia/Seoul',
          ...publication,
          result_status: 'partial',
          topic_ids: ['O08', 'O09'],
          scope: { clusters: [{ cluster_id: 'cpc-2', namespaces: ['training'] }] },
          time_range: { start: '2026-09-29T00:00:00Z', end: '2026-09-30T00:00:00Z' },
          group_by: ['namespace'],
        },
      ],
      isPending: false,
      isError: false,
      hasNextPage: false,
    };
  },
}));

describe('Ops report landing', () => {
  it.each([Reports, OperationsReports])(
    'offers one creation entry and shared filters in each view',
    (Page) => {
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/reports']}>
          <Page />
        </MemoryRouter>,
      );
      expect(html).toContain('class="button primary" href="/reports/new"');
      expect(html).toContain('전체 이력');
      expect(html.match(/href="\/reports\/new"/g)).toHaveLength(1);
      expect(html).not.toContain('Namespace GPU 현황');
      expect(html).toContain('GPU 운영 보고서 · 2개 주제');
      if (Page === Reports) {
        expect(html).not.toContain('<th>종류</th>');
        expect(html).not.toContain('<th>최종 보고서</th>');
      }
      expect(html).toContain('/reports/published#final-report');
      expect(html).not.toContain('href="/jobs/published"');
      expect(html).toContain('Namespace·프로젝트 배분 · GPU 에너지');
      expect(html).toContain('대상: cpc-2 / training');
      expect(html).toContain('분석 기간');
      expect(html).toContain('요청 집계');
      expect(html).not.toContain('>published</a>');
      expect(paths.at(-1)).not.toContain('status=succeeded');
    },
  );
  it.each([
    ['running', null],
    ['failed', null],
    ['succeeded', undefined],
  ] as const)('opens job status for unpublished %s reports', (status, resultRef) => {
    publication.status = status;
    publication.result_ref = resultRef;
    for (const Page of [Reports, OperationsReports]) {
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/reports']}>
          <Page />
        </MemoryRouter>,
      );
      expect(html).toContain('href="/jobs/published"');
      expect(html).not.toContain('href="/reports/published');
    }
  });
  it.each([Reports, OperationsReports])(
    'filters final reports while preserving the topic',
    (Page) => {
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/reports?tab=final&topic=O08']}>
          <Page />
        </MemoryRouter>,
      );
      expect(paths.at(-1)).toContain('status=succeeded');
      expect(paths.at(-1)).toContain('topic_id=O08');
      expect(html).toContain('공개된 Ops 최종 보고서');
      expect(html).toContain('자료 부족·부분 분석');
    },
  );
});

it.each(['/reports/new', '/reports/new?schedule=true'])(
  'defaults %s to namespace analysis with advanced fields collapsed',
  (path) => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={[path]}>
        <ReportForm />
      </MemoryRouter>,
    );
    expect(html).toContain(
      '<option value="namespace" selected="">Namespace별 GPU 사용 분석</option>',
    );
    expect(html).toContain('<details><summary>세부 분석 설정');
    expect(html.match(/type="checkbox" checked=""/g)).toHaveLength(
      path.includes('schedule') ? 2 : 1,
    );
    expect(html).toContain('value="namespace" selected="">Namespace');
    if (path.includes('schedule')) expect(html).toContain('직전에 완료된');
  },
);
it('names schedules by report purpose and recurrence instead of ID', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <Schedules />
    </MemoryRouter>,
  );
  expect(html).toContain('Namespace별 GPU 사용 분석');
  expect(html).toContain('cpc-2 / training');
  expect(html).toContain('매주');
  expect(html).toContain('월요일');
  expect(html).not.toContain('>published</a>');
  expect(html).not.toContain('<th>revision</th>');
});
it('preserves local report filters and rejects external return paths', () => {
  expect(reportReturnPath({ reportList: '/reports?status=failed&topic=O08' })).toBe(
    '/reports?status=failed&topic=O08',
  );
  for (const reportList of [
    'https://evil.example',
    '//evil.example',
    '/reports/other',
    '/reports#bad',
  ])
    expect(reportReturnPath({ reportList })).toBe('/reports');
  expect(reportReturnPath(null)).toBe('/reports');
});

it.each([Reports, OperationsReports])(
  'sends the selected execution filter to the existing API',
  (Page) => {
    renderToStaticMarkup(
      <MemoryRouter initialEntries={['/reports?status=failed&topic=O08']}>
        <Page />
      </MemoryRouter>,
    );
    expect(paths.at(-1)).toContain('status=failed');
    expect(paths.at(-1)).toContain('topic_id=O08');
  },
);

it('previews the complete requested period and explains worker preflight before submission', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter initialEntries={['/reports/new']}>
      <ReportForm />
    </MemoryRouter>,
  );
  expect(html).toContain('요청 전 기간 확인');
  expect(html).toContain('24시간');
  expect(html).toContain('수집 시작 전 서버');
});
