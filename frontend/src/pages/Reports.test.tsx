import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { Reports } from './Reports';
import { OperationsReports } from './Operations';

const paths = vi.hoisted(() => [] as string[]);
vi.mock('../lib/store', () => ({
  useApp: () => ({ ready: true, canOperate: true, scope: { clusters: [] } }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: (path: string) => {
    paths.push(path);
    return {
      items: [
        {
          id: 'published',
          kind: 'report',
          status: 'succeeded',
          result_ref: 'r1',
          result_status: 'partial',
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
    'exposes a prominent final-report entry in each view',
    (Page) => {
      vi.stubGlobal('location', { pathname: '/reports' });
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/reports']}>
          <Page />
        </MemoryRouter>,
      );
      expect(html).toContain('class="button primary" href="/reports?tab=final"');
      expect(html).toContain('전체 이력');
      expect(html).toContain('/reports/published#final-report');
      expect(paths.at(-1)).not.toContain('status=succeeded');
      vi.unstubAllGlobals();
    },
  );
  it.each([Reports, OperationsReports])(
    'filters final reports while preserving the topic',
    (Page) => {
      vi.stubGlobal('location', { pathname: '/reports' });
      const html = renderToStaticMarkup(
        <MemoryRouter initialEntries={['/reports?tab=final&topic=O08']}>
          <Page />
        </MemoryRouter>,
      );
      expect(paths.at(-1)).toContain('status=succeeded');
      expect(paths.at(-1)).toContain('topic_id=O08');
      expect(html).toContain('공개된 Ops 최종 보고서');
      expect(html).toContain('자료 부족·부분 분석');
      vi.unstubAllGlobals();
    },
  );
});
