import { expect, it } from 'vitest';
import { highlightSegments } from './rcaHighlight';

const marks = (text: string) =>
  highlightSegments(text)
    .filter((s) => s.mark)
    .map((s) => `${s.mark}:${s.text}`);

it('marks commands with their options, placeholders and paths but not Korean particles', () => {
  expect(marks('kubectl cordon <노드>로 새 작업 배치를 먼저 막습니다.')).toEqual([
    'command:kubectl cordon <노드>',
  ]);
  expect(
    marks('nvidia-smi -q -d ECC,ROW_REMAPPER로 확인하고 dmesg -T(또는 journalctl -k)도 봅니다.'),
  ).toEqual([
    'command:nvidia-smi -q -d ECC,ROW_REMAPPER',
    'command:dmesg -T',
    'command:journalctl -k',
  ]);
  expect(marks('cat /proc/mdstat와 --safe-mode --extra-system-data 옵션으로 실행합니다.')).toEqual([
    'command:cat /proc/mdstat',
    'command:--safe-mode --extra-system-data',
  ]);
});

it('stops option values at Korean and skips log keywords that only look like commands', () => {
  expect(marks('nvidia-smi --query-gpu=gpu_recovery_action --format=csv로 확인합니다.')).toEqual([
    'command:nvidia-smi --query-gpu=gpu_recovery_action --format=csv',
  ]);
  expect(
    marks('EXT4-fs error·nvme·md/raid 줄을 저장하고 nvme smart-log <장치>로 기록합니다.'),
  ).toEqual(['command:nvme smart-log <장치>']);
});

it('marks prohibitions before disruptive actions and leaves plain verbs alone', () => {
  expect(marks('커널 로그에 없으면 재시작하지 않고 보고 경로부터 확인합니다.')).toEqual([
    'caution:재시작하지 않고',
  ]);
  expect(marks('작업 배출·유지보수 승인 후 호스트를 재시작합니다.')).toEqual([
    'action:작업 배출',
    'action:호스트를 재시작합니다',
  ]);
  expect(marks('복구 조치를 하지 않고 확인합니다.')).toEqual(['caution:조치를 하지 않고']);
  // Analysis caveats and mere mentions are not emphasised.
  expect(marks('동시 발생만으로 원인 관계를 확정하지 않습니다. 리셋 뒤 다시 봅니다.')).toEqual([]);
  expect(marks('같은 GPU에서 다시 나는지 확인합니다.')).toEqual([]);
  // Segments always reassemble into the original sentence.
  const text = '재시작하면 커널 로그가 사라지므로 먼저 nvidia-bug-report.sh를 실행합니다.';
  expect(
    highlightSegments(text)
      .map((s) => s.text)
      .join(''),
  ).toBe(text);
});
