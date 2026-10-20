import { obj, rows, str, type Row } from './live';
import { rcaReasons } from './rcaLabels';

// Explain stored gaps without promoting a report to a verified device state.
export function gapMeaning(code: string, result: Row): string | undefined {
  const analysis = obj(obj(result.quality).analysis);
  if (
    code === 'causal_confirmation_evidence' &&
    ['alert_match', 'goal_achieved'].includes(str(analysis.collection_stop_reason)) &&
    (str(analysis.collection_stop_reason) === 'alert_match' ||
      (Array.isArray(analysis.out_of_scope) &&
        analysis.out_of_scope.includes('causal_confirmation_evidence')))
  ) {
    return '이번 조사는 알림에 해당하는 오류 보고를 확인하는 범위에서 완료됐습니다. 물리적인 고장 원인을 찾는 조사는 포함하지 않았습니다. 이 항목이 남아 있는 과거 결과의 부분 산출 표시는 당시 저장된 판정입니다.';
  }
  if (code === 'synthesis_failed') {
    const reason = str(obj(obj(obj(result.quality).analysis).synthesis).error_code);
    if (reason) return `${rcaReasons[reason] || '분석 실패 사유'} (${reason})`;
  }
  const observed = rows(obj(result.quality).evidence_catalog).some(
    (e) =>
      str(e.label).startsWith('D09') && typeof e.sample_count === 'number' && e.sample_count > 0,
  );
  const meanings: Record<string, string> = {
    causal_confirmation_evidence: observed
      ? '오류 관련 로그는 수집했지만 실제 원인을 확정할 근거는 부족합니다. 보고된 증상과 원인 후보를 구분해야 합니다.'
      : '보고된 증상만으로 실제 원인을 확정할 수 없습니다. 후보를 지지하거나 반박할 추가 근거가 필요합니다.',
    normalized_health:
      '로그의 상태 보고를 실제 장치의 현재 상태로 검증하지 못했습니다. 오류가 지금도 지속되는지 확인해야 합니다.',
    producer_contract:
      '생산자 정보가 없다는 뜻이 아닙니다. Runbook이 요구하는 검증된 상태 근거의 조건을 충족하지 못했습니다.',
    unknown_value:
      '수집된 값을 검증 가능한 의미로 해석하지 못했다는 포괄적 사유입니다. 함께 표시된 상태·신원·시각 조건을 먼저 확인하세요.',
  };
  return meanings[code];
}
