import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RangeCalendar, monthCells, pickDay, shiftMonth } from './RangeCalendar';
import { dayRange } from '../lib/incidentOverview';

it('lays out a month from Sunday with blanks before the 1st', () => {
  // 2026-10-01 is a Thursday.
  const cells = monthCells('2026-10');
  expect(cells.slice(0, 5)).toEqual(['', '', '', '', '2026-10-01']);
  expect(cells.at(-1)).toBe('2026-10-31');
  expect(monthCells('2028-02').at(-1)).toBe('2028-02-29');
  expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  expect(shiftMonth('2026-12', 1)).toBe('2027-01');
});

it('starts a range on the first click and orders it on the second; one day twice is that day', () => {
  expect(pickDay('', '2026-10-20')).toEqual({ anchor: '2026-10-20' });
  expect(pickDay('2026-10-20', '2026-10-13')).toEqual({ first: '2026-10-13', last: '2026-10-20' });
  expect(pickDay('2026-10-20', '2026-10-20')).toEqual({ first: '2026-10-20', last: '2026-10-20' });
});

it('lists inclusive KST days across a month boundary', () => {
  expect(dayRange('2026-09-29', '2026-10-02')).toEqual([
    '2026-09-29',
    '2026-09-30',
    '2026-10-01',
    '2026-10-02',
  ]);
  expect(dayRange('2026-10-02', '2026-10-01')).toEqual([]);
});

it('starts closed with the selected range as its label', () => {
  const html = renderToStaticMarkup(
    <RangeCalendar
      first="2026-10-13"
      last="2026-10-27"
      today="2026-10-27"
      label="최근 14일"
      onChange={() => {}}
    />,
  );
  expect(html).toContain('aria-expanded="false"');
  expect(html).toContain('최근 14일');
  expect(html).not.toContain('role="dialog"');
});
