import { expect, it } from 'vitest';
import { gapMeaning } from './rcaGuidance';

it('does not infer successful collection from a gap code alone', () => {
  expect(gapMeaning('causal_confirmation_evidence', {})).not.toContain('로그는 수집했지만');
  expect(
    gapMeaning('causal_confirmation_evidence', {
      quality: { evidence_catalog: [{ label: 'D09 로그', sample_count: 0 }] },
    }),
  ).not.toContain('로그는 수집했지만');
  expect(
    gapMeaning('causal_confirmation_evidence', {
      quality: { evidence_catalog: [{ label: 'D09 로그', sample_count: 30 }] },
    }),
  ).toContain('로그는 수집했지만');
  expect(gapMeaning('future_code', {})).toBeUndefined();
});

it('distinguishes producer identity from eligibility of state evidence', () => {
  expect(gapMeaning('producer_contract', {})).toContain('생산자 정보가 없다는 뜻이 아닙니다');
  expect(gapMeaning('normalized_health', {})).toContain('현재 상태로 검증하지 못했습니다');
});

it('explains scoped completion in historical results without rewriting stored status', () => {
  const result = {
    result_status: 'partial',
    quality: { analysis: { collection_stop_reason: 'alert_match' } },
  };
  const before = JSON.stringify(result);
  expect(gapMeaning('causal_confirmation_evidence', result)).toContain('범위에서 완료');
  expect(gapMeaning('causal_confirmation_evidence', result)).not.toContain('추가 근거가 필요');
  expect(JSON.stringify(result)).toBe(before);
});
