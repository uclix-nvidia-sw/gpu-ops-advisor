import { Children, isValidElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it, vi } from 'vitest';
import { ReportDeleteButton, ReportDeleteDialog, ReportDeletionNotice } from './ReportDeletion';
import type { Row } from '../lib/live';

const state = vi.hoisted(() => ({
  reason: '',
  busy: false,
  error: '',
  run: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useState: (initial: unknown) => [initial === '' ? state.reason : initial, vi.fn()],
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({ notify: state.notify, refresh: state.refresh }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useCommand: () => state,
}));
const job: Row = {
  id: 'report-1',
  kind: 'report',
  status: 'succeeded',
  version: 7,
  can_delete: true,
  topic_ids: ['O08'],
};
const deletion = {
  deleted_at: '2026-10-12T00:00:00Z',
  reason: '검증용 보고서 정리',
  evidence_count: 11,
  artifact_cleanup_state: 'pending',
};
beforeEach(() => {
  state.reason = '';
  state.busy = false;
  state.error = '';
  state.run.mockReset();
  state.notify.mockReset();
  state.refresh.mockReset();
});
function find(node: ReactNode, type: string): Record<string, unknown> | undefined {
  for (const child of Children.toArray(node)) {
    if (!isValidElement<Record<string, unknown>>(child)) continue;
    if (child.type === type) return child.props;
    const found = find(child.props.children as ReactNode, type);
    if (found) return found;
  }
}
function dialog(onClose = vi.fn()) {
  const element = ReportDeleteDialog({ job, onClose });
  return {
    element,
    onClose,
    submit: find(element, 'form')!.onSubmit as (e: { preventDefault: () => void }) => Promise<void>,
  };
}
it('only offers deletion with the explicit report capability and a known version', () => {
  expect(renderToStaticMarkup(<ReportDeleteButton job={job} />)).toContain('보고서 삭제');
  for (const overrides of [
    { kind: 'rca' },
    { can_delete: false },
    { can_delete: undefined },
    { version: undefined },
    { version: 0 },
    { deletion },
  ]) {
    expect(renderToStaticMarkup(<ReportDeleteButton job={{ ...job, ...overrides }} />)).toBe('');
  }
});
it('explains permanent own-data deletion and protects shared references before confirming', () => {
  const html = renderToStaticMarkup(dialog().element);
  for (const text of [
    '영구 삭제',
    '모든 시도',
    '복구할 수 없습니다',
    '작업·시도 이력과 삭제 기록',
    '원본 RCA 조사와 다른 보고서는 유지',
    '사용 중이면 삭제하지 않습니다',
    '삭제 사유',
  ])
    expect(html).toContain(text);
  expect(html).toContain('required=""');
  expect(html).toContain('disabled=""');
});
it('submits the current version through the idempotent command path and closes only on success', async () => {
  state.reason = '  검증용 보고서 정리  ';
  state.run.mockResolvedValue({ deletion });
  const { submit, onClose } = dialog();
  await submit({ preventDefault: vi.fn() });
  expect(state.run).toHaveBeenCalledWith(
    '/jobs/report-1/delete',
    { reason: '검증용 보고서 정리' },
    { version: 7, idempotent: true },
  );
  expect(onClose).toHaveBeenCalledOnce();
  expect(state.notify).toHaveBeenCalledOnce();
});
it.each(['', '   '])('rejects an empty reason %j without sending a command', async (reason) => {
  state.reason = reason;
  await dialog().submit({ preventDefault: vi.fn() });
  expect(state.run).not.toHaveBeenCalled();
});
it('prevents a second submission or closing while deletion is pending', async () => {
  state.reason = '검증용';
  state.busy = true;
  const { element, submit, onClose } = dialog();
  await submit({ preventDefault: vi.fn() });
  element.props.onClose();
  expect(state.run).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  expect(renderToStaticMarkup(element)).toContain('삭제 처리 중…');
});
it.each([
  '다른 분석이나 운영 기록에서 사용하는 근거가 있어 삭제할 수 없습니다.',
  '작업이 변경되었습니다.',
  '소유 모듈에 연결할 수 없습니다.',
])('keeps the dialog and reason after failure: %s', async (error) => {
  state.reason = '검증용 보고서 정리';
  state.error = error;
  state.run.mockResolvedValue(undefined);
  const { element, submit, onClose } = dialog();
  await submit({ preventDefault: vi.fn() });
  expect(onClose).not.toHaveBeenCalled();
  expect(state.notify).not.toHaveBeenCalled();
  const html = renderToStaticMarkup(element);
  expect(html).toContain(error);
  expect(html).toContain('검증용 보고서 정리');
  expect(html).toContain('현재 상태 다시 확인');
});
it.each([
  ['pending', '정리 대기 · 자동으로 진행합니다.'],
  ['failed', '정리 지연 · 자동으로 다시 시도합니다.'],
  ['complete', '정리 완료'],
  ['unknown', '정리 상태 미확인'],
])(
  'shows %s cleanup without claiming files are already removed',
  (artifact_cleanup_state, text) => {
    const html = renderToStaticMarkup(
      <ReportDeletionNotice job={{ ...job, deletion: { ...deletion, artifact_cleanup_state } }} />,
    );
    expect(html).toContain(text);
    expect(html).toContain('11건');
    expect(html).toContain('2026. 10. 12. 09:00:00');
    expect(html).not.toContain('원본 결과 보기');
  },
);
