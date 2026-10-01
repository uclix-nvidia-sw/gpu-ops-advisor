import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReportOrigin } from './ReportMeta';
import { DataView } from './live';

it('distinguishes scheduled, manual and unknown origins without guessing', () => {
  for (const [value, label] of [
    ['schedule', '자동 생성'],
    ['manual', '직접 요청'],
    [undefined, '생성 방식 미확인'],
    ['legacy', '생성 방식 미확인'],
  ]) {
    expect(renderToStaticMarkup(<ReportOrigin value={value} />)).toContain(`생성 방식: ${label}`);
  }
});
it('renders report timestamps in Korea time across a day boundary without changing durations or raw values', () => {
  const value = {
    period: { start: '2026-09-30T15:00:00Z', end: '2026-10-01T16:00:00+01:00' },
    timezone: 'UTC',
    duration_seconds: 86400,
  };
  const html = renderToStaticMarkup(<DataView value={value} reportDisplay />);
  expect(html).toContain('10. 01.');
  expect(html).toContain('10. 02.');
  expect(html).not.toContain('T15:00:00Z');
  expect(html).not.toContain('UTC');
  expect(html).toContain('86400');
  expect(renderToStaticMarkup(<DataView value={value} />)).toContain('2026-09-30T15:00:00Z');
  expect(value.period.start).toBe('2026-09-30T15:00:00Z');
});
