import { Children, isValidElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { AggregateReportForm } from './AggregateReportForm';
import { LegacyReportForm } from './Reports';
import { ScheduleEditor } from './Schedules';

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  drafts: {} as Record<string, unknown>,
  legacyFrequency: 'daily',
  run: vi.fn(),
  setError: vi.fn(),
}));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useState: (initial: unknown) => [initial === 'daily' ? state.legacyFrequency : initial, vi.fn()],
}));
vi.mock('react-router-dom', async (original) => ({
  ...(await original<typeof import('react-router-dom')>()),
  useSearchParams: () => [state.params, vi.fn()],
  useNavigate: () => vi.fn(),
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({ mode: 'operations', canOperate: true, scope: { clusters: [] } }),
}));
vi.mock('../lib/newDraft', () => ({
  useNewDraft: (key: string, initial: unknown) => [state.drafts[key] ?? initial, vi.fn()],
  clearNewDraft: vi.fn(),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useCommand: () => ({ ...state, busy: false, error: '' }),
}));
beforeEach(() => {
  state.params = new URLSearchParams();
  state.drafts = { 'report/manual/lastDay': '2026-10-22' };
  state.legacyFrequency = 'daily';
  state.run.mockReset();
  state.setError.mockReset();
});
function form(node: ReactNode): Record<string, unknown> | undefined {
  for (const child of Children.toArray(node)) {
    if (!isValidElement<Record<string, unknown>>(child)) continue;
    if (child.type === 'form') return child.props;
    const found = form(child.props.children as ReactNode);
    if (found) return found;
  }
}
const submit = (element: ReactNode) =>
  (form(element)!.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({
    preventDefault: vi.fn(),
  });
const render = (element: ReactNode) => renderToStaticMarkup(<MemoryRouter>{element}</MemoryRouter>);

it.each([false, true])('offers only daily aggregate creation (scheduled=%s)', async (scheduled) => {
  state.drafts['report/manual/scheduled'] = scheduled;
  const element = AggregateReportForm();
  const html = render(element);
  expect(html).toContain('value="daily"');
  expect(html).not.toContain('value="weekly"');
  expect(html).not.toContain('실행 요일');
  await submit(element);
  expect(state.run).toHaveBeenCalledOnce();
  const [path, body] = state.run.mock.calls[0];
  expect(path).toBe(scheduled ? '/schedules' : '/reports');
  if (scheduled) {
    expect(body).toMatchObject({
      frequency: 'daily',
      period: 'previous_complete_day',
      local_time: '09:00',
    });
    expect(body).not.toHaveProperty('weekday');
  } else {
    expect(body.time_range).toEqual({
      start: '2026-10-21T15:00:00.000Z',
      end: '2026-10-22T15:00:00.000Z',
    });
  }
});
it.each([false, true])(
  'blocks a restored weekly aggregate draft (scheduled=%s)',
  async (scheduled) => {
    state.drafts['report/manual/scheduled'] = scheduled;
    state.drafts['report/manual/frequency'] = 'weekly';
    const element = AggregateReportForm();
    expect(render(element)).toContain('분석 기간을 다시 선택하세요');
    expect(render(element)).toMatch(/type="submit" disabled=""/);
    await submit(element);
    expect(state.run).not.toHaveBeenCalled();
    expect(state.setError).toHaveBeenCalledWith(expect.stringContaining('일일만 지원'));
  },
);
it('hides weekly legacy scheduling and rejects a stale weekly submission', async () => {
  state.params.set('schedule', 'true');
  expect(render(LegacyReportForm())).not.toContain('value="weekly"');
  state.legacyFrequency = 'weekly';
  await submit(LegacyReportForm());
  expect(state.run).not.toHaveBeenCalled();
  expect(state.setError).toHaveBeenCalledWith(expect.stringContaining('신규 주간 일정'));
});
const schedule = {
  id: 's1',
  frequency: 'daily',
  local_time: '09:00',
  timezone: 'Asia/Seoul',
  version: 3,
  report_spec: { topic_ids: ['namespace_usage', 'incident_summary'] },
};
it('does not offer a weekly conversion and blocks its restored edit draft', async () => {
  expect(render(ScheduleEditor({ initial: schedule, onClose: vi.fn() }))).not.toContain(
    'value="weekly"',
  );
  state.drafts['schedule/s1/frequency'] = 'weekly';
  const element = ScheduleEditor({ initial: schedule, onClose: vi.fn() });
  expect(render(element)).toContain('반복 주기를 다시 선택하세요');
  await submit(element);
  expect(state.run).not.toHaveBeenCalled();
});
it('preserves an existing weekly schedule instead of silently changing its period', async () => {
  const element = ScheduleEditor({
    initial: { ...schedule, frequency: 'weekly', weekday: 3 },
    onClose: vi.fn(),
  });
  expect(render(element)).toContain('value="weekly"');
  await submit(element);
  expect(state.run).toHaveBeenCalledWith(
    '/schedules/s1',
    {
      frequency: 'weekly',
      period: 'previous_complete_week',
      weekday: 3,
      local_time: '09:00',
      timezone: 'Asia/Seoul',
    },
    { method: 'PATCH', version: 3 },
  );
});
it('keeps daily schedule edits available', async () => {
  await submit(ScheduleEditor({ initial: schedule, onClose: vi.fn() }));
  expect(state.run).toHaveBeenCalledWith(
    '/schedules/s1',
    expect.objectContaining({
      frequency: 'daily',
      period: 'previous_complete_day',
    }),
    { method: 'PATCH', version: 3 },
  );
});
