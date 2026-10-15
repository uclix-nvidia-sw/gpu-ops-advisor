import labels from './rcaLabels.json';
import { obj, rows, type Row } from './live';

export const rcaLabels = labels;
export const rcaReasons: Record<string, string> = labels.reasons;

// A final draft's review status does not describe whether a request was sent.
export function modelExecution(stage: Row): string {
  const usage = obj(stage.usage);
  const attempts = stage.request_attempts ?? usage.request_attempts;
  const responses = stage.response_calls ?? usage.calls;
  if (
    (typeof attempts === 'number' && attempts > 0) ||
    (typeof responses === 'number' && responses > 0)
  )
    return `모델 전송 시도 ${typeof attempts === 'number' ? attempts : '미기록'}회 · 응답 기록 ${typeof responses === 'number' ? responses : '미기록'}건`;
  const checks = rows(stage.request_checks);
  if (checks.some((c) => c.model_called === true)) return '논리 모델 요청 실행 · 전송 여부 미확인';
  if (
    (attempts === 0 && responses === 0) ||
    (checks.length > 0 && checks.every((c) => c.model_called === false))
  )
    return '모델 호출 전 생략';
  return '모델 호출 여부 미확인 · 단계별 기록 없음';
}
// UI classification only; stored result quality and evidence remain unchanged.
const categories = [
  {
    id: 'collection',
    name: '원본 조회·수집 문제',
    codes: [
      'query_failed',
      'observation_degraded',
      'mapping_source_unavailable',
      'no_usable_evidence',
      'observations',
      'binding_unselected',
      'binding_scope_unavailable',
    ],
    next: '수집 근거에서 실패·빈 응답·부분 수집인 D와 조회 구간을 확인하세요. 연결·권한·한도를 해결한 뒤 필요한 조회를 검토하세요.',
  },
  {
    id: 'identity',
    name: '장치 신원·사건 시각 연결 미확인',
    codes: [
      'incident_mapping',
      'mapping_target_unverified',
      'mapping_not_observed_at_incident',
      'target_identity_conflict',
      'current_mapping',
      'topology',
    ],
    next: '알람의 노드·GPU UUID·PCI와 사건 시각의 관측 대상을 대조하세요. 식별자가 없으면 특정 GPU 고장으로 단정하지 않습니다.',
  },
  {
    id: 'semantics',
    name: '상태·값의 의미 검증 필요',
    codes: [
      'producer_contract',
      'error_code',
      'normalized_health',
      'reported_error_code',
      'reported_producer_contract',
      'unknown_value',
      'binding_unverified',
      'binding_semantics_or_samples_missing',
      'observation_conflicted',
      'conflicting_evidence',
    ],
    next: '원본 보고와 검증된 현재 상태를 구분하세요. 생산자 계약·유효 시각·단위·상충 관측을 확인해야 하며, 데이터가 없다는 뜻으로 해석하지 않습니다.',
  },
  {
    id: 'model',
    name: 'LLM 분석·응답 검증 문제',
    codes: [],
    next: '분석 실패 사유와 수정 요청 진단에서 근거 참조·응답 형식·숫자 검증·예산 또는 시간을 점검하세요. 조회 실패와는 별개입니다.',
  },
  {
    id: 'runbook',
    name: '조사 절차·Runbook 확인 필요',
    codes: ['approved_runbook', 'invalid_contract'],
    next: '선택·탈락한 Runbook revision과 계약 진단을 확인하세요. 필요한 근거를 확보할 수 있는 조사 절차인지 검토하세요.',
  },
  {
    id: 'cause',
    name: '원인 확정을 위한 추가 검토',
    codes: ['causal_confirmation_evidence'],
    next: '보고된 증상은 원인 확정과 다릅니다. 후보를 지지·반박하는 근거를 대조하고 담당자가 판단하세요. 이 항목만으로 조회 또는 LLM 실패를 뜻하지 않습니다.',
  },
  {
    id: 'other',
    name: '기타 요구 조건·미분류 사유',
    codes: [],
    next: '원문 사유와 조사별 판단을 확인하세요. 알려지지 않은 코드를 수집 실패나 정상으로 추정하지 않습니다.',
  },
];
export function missingGroups(codes: string[]) {
  return categories
    .map((group) => ({
      ...group,
      items: [...new Set(codes)].filter((code) => {
        const assigned =
          categories.find((g) => g.codes.includes(code))?.id ??
          (/^(synthesis_|llm_)/.test(code) ? 'model' : 'other');
        return assigned === group.id;
      }),
    }))
    .filter((group) => group.items.length);
}
export function purposeLabel(id: string) {
  const names: Record<string, string> = labels.purposes;
  const required: Record<string, string> = labels.required;
  return `${id} ${names[id] || '목적 미확인'} — ${required[id] || '필수 근거 미확인'}`;
}
