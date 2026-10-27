import { expect, it } from 'vitest';
import { knowledgeActions } from './Knowledge';

it('offers discard for every revision that is not retired', () => {
  const actions = (state: string) => knowledgeActions(state).map(([v]) => v);
  expect(actions('draft')).toEqual(['request', 'retire']);
  expect(actions('in_review')).toEqual(['approve', 'request_changes', 'retire']);
  expect(actions('reviewed')).toEqual(['publish', 'retire']);
  expect(actions('published')).toEqual(['retire']);
  expect(actions('retired')).toEqual([]);
});
