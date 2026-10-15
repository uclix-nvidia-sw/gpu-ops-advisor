import { expect, it } from 'vitest';
import { modelExecution } from './rcaLabels';

it.each([
  [{ request_attempts: 0, response_calls: 0 }, '모델 호출 전 생략'],
  [{ request_checks: [{ model_called: false }] }, '모델 호출 전 생략'],
  [
    { execution_status: 'skipped', usage: { request_attempts: 1, calls: 1 } },
    '모델 전송 시도 1회 · 응답 기록 1건',
  ],
  [{ usage: { request_attempts: 1, calls: 0 } }, '모델 전송 시도 1회 · 응답 기록 0건'],
  [
    { request_checks: [{ model_called: true }, { model_called: false }] },
    '논리 모델 요청 실행 · 전송 여부 미확인',
  ],
  [{ execution_status: 'skipped' }, '모델 호출 여부 미확인'],
  [{ request_checks: [{}] }, '모델 호출 여부 미확인'],
])('uses explicit call evidence instead of final status: %j', (stage, expected) => {
  expect(modelExecution(stage)).toContain(expected);
});
