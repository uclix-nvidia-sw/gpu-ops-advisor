import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { RcaLink } from './IncidentOverview';
import { incidentView } from '../lib/incidentOverview';

const render = (status: string, published = false) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/cases?q=SXID11021&page=2']}>
      <RcaLink
        v={incidentView({
          target: {},
          rca_summary: {
            latest_job: { job_id: 'latest', status },
            latest_published: published ? { job_id: 'old', result_status: 'partial' } : null,
          },
        })}
      />
    </MemoryRouter>,
  );

it.each([
  ['queued', '실행 대기'],
  ['running', 'RCA 실행 중'],
  ['retry_wait', '재시도 대기'],
  ['failed', '실행 실패'],
  ['cancelled', '취소 완료'],
  ['expired', '기한 만료'],
  ['succeeded', '실행 완료 · 미발행'],
  ['unrecognized', '상태 미확인'],
])('links %s to its execution without inventing a published result', (status, label) => {
  const html = render(status);
  expect(html).toContain(label);
  expect(html).toContain('href="/jobs/latest"');
  expect(html).not.toContain('#final-report');
});

it('keeps the old report accessible while the latest attempt waits for retry', () => {
  const html = render('retry_wait', true);
  expect(html).toContain('재시도 대기');
  expect(html).toContain('이전 보고서 열기');
  expect(html).toContain('href="/analyses/old#final-report"');
  expect(html).toContain('href="/jobs/latest"');
});
