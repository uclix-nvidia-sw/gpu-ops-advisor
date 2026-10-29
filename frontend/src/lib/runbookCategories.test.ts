import { expect, it } from 'vitest';
import { runbookCategories } from './runbookCategories';
it('classifies saved metadata with overlap without mining remediation text', () => {
  expect(
    runbookCategories({
      kind: 'runbook',
      content: { search: { codes: ['xid:92'] }, classification: { domain: 'GPU_MEMORY' } },
    }),
  ).toEqual(['XID', 'Memory']);
  expect(
    runbookCategories({ kind: 'runbook', content: { search: { codes: ['sxid:11001'] } } }),
  ).toEqual(['SXID']);
  expect(
    runbookCategories({
      kind: 'runbook',
      content: { search: { producer_events: ['disk'] }, description: 'Check memory and network' },
    }),
  ).toEqual(['Disk']);
  expect(runbookCategories({ kind: 'runbook', content: { title: 'XID 99 memory' } })).toEqual([
    '기타',
  ]);
  expect(runbookCategories({ kind: 'policy', content: { search: { codes: ['xid:92'] } } })).toEqual(
    [],
  );
});
