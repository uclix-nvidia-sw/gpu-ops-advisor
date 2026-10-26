import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { componentInfo, matchedReasons } from './componentReasons';

const book = (key: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../../rcca-agent/runbooks/component/${key}.json`, import.meta.url),
      'utf8',
    ),
  ).content.operator_guidance;

it('matches Fleet reasons, including several joined in one report', () => {
  expect(
    matchedReasons('disk', 'filesystem remounted as read-only due to errors').map((r) => r.label),
  ).toEqual(['읽기 전용 재마운트']);
  expect(
    matchedReasons(
      'disk',
      'NVME controller I/O timeout detected, attempting reset, Buffer I/O error detected on device',
    ).map((r) => r.label),
  ).toEqual(['NVMe I/O 타임아웃', '버퍼 I/O 오류']);
  expect(matchedReasons('cpu', 'error calculating CPU usage').map((r) => r.label)).toEqual([
    'CPU 사용률 계산 실패',
  ]);
  expect(matchedReasons('disk', 'something new')).toEqual([]);
  expect(componentInfo('accelerator-nvidia-dcgm-mem').target).toContain('dcgm_incidents');
  expect(componentInfo('kubelet').short).toBe('장치 정보 없음');
});

it('names only judgment branches the shipped Runbooks actually contain', () => {
  for (const [component, key] of [
    ['disk', 'RB-COMPONENT-DISK'],
    ['accelerator-nvidia-persistence-mode', 'RB-COMPONENT-PERSISTENCE-MODE'],
  ]) {
    const judge = book(key).next_checks.find((c: { title: string }) => c.title.startsWith('판단'))
      .text as string;
    for (const reason of componentInfo(component).reasons)
      if (reason.branch) expect(judge).toContain(`${reason.branch}:`);
  }
});
