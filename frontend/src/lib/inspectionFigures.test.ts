import { readdirSync, readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { INSPECTION_STEPS, inspectionFigures } from './inspectionFigures';

const BOOKS = new URL('../../../rcca-agent/runbooks/', import.meta.url);
const books = ['xid', 'sxid', 'component'].flatMap((dir) =>
  readdirSync(new URL(`${dir}/`, BOOKS)).map(
    (f) => JSON.parse(readFileSync(new URL(`${dir}/${f}`, BOOKS), 'utf8')).content,
  ),
);
const stepsFor = (key: string) =>
  books
    .filter(
      (c) =>
        (c.search?.codes || []).includes(key) ||
        c.decision_policy?.applies_when?.reported_component === key,
    )
    .flatMap((c) => c.operator_guidance.next_checks.map((s: { title: string }) => s.title));

it('maps only steps that exist in the repository Runbooks', () => {
  for (const [key, steps] of Object.entries(INSPECTION_STEPS)) {
    const titles = stepsFor(key);
    expect(titles.length, key).toBeGreaterThan(0);
    for (const step of Object.keys(steps)) expect(titles, key).toContain(step);
  }
});

it('places GPU figures for XID 79 and only the SXM NVSwitch figure for SXID 11001', () => {
  const xid79 = inspectionFigures('XID:79', stepsFor('xid:79'));
  expect([...xid79]).toEqual([['복구: 호스트 재시작 (RESTART_BM)', ['S1', 'P1']]]);
  const sxid = inspectionFigures('SXID:11001', stepsFor('sxid:11001'));
  expect([...sxid]).toEqual([['공급사 전달 (재발)', ['S2']]]);
});

it('shows no figure for unmapped codes, missing steps or a code match alone', () => {
  expect(inspectionFigures('xid:13', stepsFor('xid:13')).size).toBe(0);
  expect(inspectionFigures('kubelet', ['즉시 확인', '복구']).size).toBe(0);
  expect(inspectionFigures('xid:79', ['즉시 확인·격리', '복구 확인']).size).toBe(0);
  expect(inspectionFigures('', []).size).toBe(0);
});

it('maps each figure to at most one step per code so a report shows it once', () => {
  for (const [key, steps] of Object.entries(INSPECTION_STEPS)) {
    const ids = Object.values(steps).flat();
    expect(new Set(ids).size, key).toBe(ids.length);
  }
});
