import { obj, rows, str, strings, type Row } from '../lib/live';
import { evaluationLabels } from './RcaEvaluation';
import { modelExecution, rcaReasons } from '../lib/rcaLabels';

export const rcaStages: Record<string, { title: string; actor: string; purpose: string }> = {
  rca_result_frozen: {
    title: '보고서용 RCA 근거 자료 고정',
    actor: '코드',
    purpose: '관측·분석·권고 자료와 근거 참조를 고정하여 보고서 작성 전후의 변경을 검사합니다.',
  },
  report_assembly: {
    title: '최종 보고서 작성',
    actor: '코드 · 선택적 문장 정렬 LLM',
    purpose:
      '채택한 분석과 한계·종료 이유를 보고서로 구성합니다. 원인을 새로 분석하지 않으며 저장·공개 여부는 작업 결과에서 확인합니다.',
  },
  evidence_validation: {
    title: '기초 검증',
    actor: '코드',
    purpose: '형식·시각·문자열 비교. 의미나 동일 장비 여부를 확정하지 않습니다.',
  },
  evidence_interpretation: {
    title: '증거 해석',
    actor: 'LLM ①',
    purpose: '보고된 사실·추론·미확인·상충을 분리합니다.',
  },
  rca_synthesis: {
    title: 'RCA 분석 작성',
    actor: 'LLM ②',
    purpose: '근거 범위에서 원인 후보와 한계를 작성합니다.',
  },
  rca_analysis_draft: {
    title: '검토할 초안 고정',
    actor: '코드',
    purpose: 'Runbook 후보·권고를 결합하고 입력과 초안을 hash로 고정합니다.',
  },
  analysis_review: {
    title: '분석 품질 검토',
    actor: 'LLM ③ + 코드',
    purpose: '6개 척도의 이유·근거를 검토합니다. 원인 확정 판정은 아닙니다.',
  },
  investigation_decision: {
    title: '다음 행동 결정',
    actor: '코드',
    purpose: '주장 보류·보완 수집·기존 판단 유지·종료를 결정합니다.',
  },
};
export function stageForRecord(record: Row, related: Row[] = []) {
  const kind = str(record.query_id);
  const body = { ...obj(record.quality), ...obj(record.snapshot) };
  if (body.workflow === 'single_collection') {
    const current: Record<string, { title: string; actor: string; purpose: string }> = {
      rca_synthesis: {
        title: '관측 자료 분석',
        actor: '작성 LLM',
        purpose: '수집된 로그·메트릭·host 이력을 함께 읽고 근거에 연결된 분석을 작성합니다.',
      },
      rca_analysis_draft: {
        title: '분석·권고 자료 저장',
        actor: '코드',
        purpose: '형식과 근거 참조를 검사한 분석에 런북 권고를 연결하고 입력과 결과를 보존합니다.',
      },
    };
    if (current[kind]) return current[kind];
  }
  const combined = body.generation_mode === 'combined';
  const sent = Number(obj(body.usage).request_attempts) > 0 || Number(obj(body.usage).calls) > 0;
  if (kind === 'report_assembly' && obj(body.report).presentation === 'rca-material/1')
    return {
      title: '최종 보고서 서술',
      actor: '보고서 LLM + 코드 검증',
      purpose:
        '고정된 RCA 자료를 완성된 문장으로 구성합니다. 원본 재분석·별도 문장 정렬 호출은 없습니다. 실패하면 RCA 자료를 기본 표시합니다.',
    };
  if (kind === 'analysis_review' && body.execution_status === 'skipped')
    return {
      title: body.reason === 'draft_changed_after_review' ? '변경 초안 미검토' : '품질 검토 미실행',
      actor: sent ? '검토 LLM · 최종 상태 기록' : '코드 · 상태 기록',
      purpose:
        body.reason === 'draft_changed_after_review'
          ? '초안이 바뀌어 이전 검토 결과를 적용할 수 없습니다. 최종 초안은 미검토 상태입니다.'
          : '품질 검토를 실행하지 않은 이유를 기록했습니다.',
    };
  if (
    kind === 'rca_analysis_draft' &&
    (body.reason === 'review_claims_withheld' ||
      (typeof record.job_id === 'string' &&
        typeof record.attempt_no === 'number' &&
        typeof body.analysis_id === 'string' &&
        body.analysis_id.length > 0 &&
        related.some((r) => {
          const review = { ...obj(r.quality), ...obj(r.snapshot) };
          return (
            r.query_id === 'analysis_review' &&
            review.analysis_id === body.analysis_id &&
            review.reason === 'draft_changed_after_review' &&
            review.execution_status === 'skipped' &&
            review.attempts === 0 &&
            r.job_id === record.job_id &&
            r.attempt_no === record.attempt_no
          );
        })))
  )
    return {
      ...rcaStages.rca_analysis_draft,
      title:
        body.reason === 'review_claims_withheld'
          ? '주장 제외 후 초안 저장'
          : '검토 후 변경 초안 저장',
      purpose:
        body.reason === 'review_claims_withheld'
          ? '검토에서 지적한 주장을 제외하고 관련 권고를 보류한 초안을 저장했습니다. 새 LLM 호출은 없습니다.'
          : '같은 초안 식별값에 변경 후 미검토 기록이 연결되어 있습니다. 이전 초안의 검토 결과를 적용하지 않습니다.',
    };
  if (kind === 'investigation_decision' && body.action === 'withhold')
    return { ...rcaStages.investigation_decision, title: '검토 지적에 따라 주장 제외' };
  if (combined && kind === 'rca_synthesis')
    return {
      title: '증거 해석·RCA 분석',
      actor: '작성 LLM',
      purpose:
        '한 응답에서 보고된 사실·미확인·원인 후보를 구분합니다. 품질 검토는 별도로 진행합니다.',
    };
  if (combined && kind === 'analysis_review')
    return { ...rcaStages.analysis_review, actor: '별도 검토 LLM + 코드' };
  return rcaStages[kind];
}
const label = (v: unknown) => evaluationLabels[str(v)] || rcaReasons[str(v)] || str(v, '기록 없음');
const amount = (v: unknown) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('ko-KR') : '기록 없음';

export function reviewStatus(record: Row) {
  const body = { ...obj(record.quality), ...obj(record.snapshot) };
  if (record.query_id !== 'analysis_review') return null;
  if (body.execution_status === 'skipped')
    return body.attempts === 0 &&
      !(Number(obj(body.usage).request_attempts) > 0 || Number(obj(body.usage).calls) > 0)
      ? '미실행'
      : '미검토';
  if (body.execution_status === 'complete') {
    const verdict = obj(body.review).verdict ?? body.verdict;
    return `검토 완료 · ${verdict == null ? '판정 미기록' : label(verdict)}`;
  }
  return null;
}

const validationMeaning: Record<string, string> = {
  object_type: 'JSON 객체여야 하는 항목의 타입이 다릅니다.',
  list_type: '목록이어야 하는 항목의 타입이 다릅니다.',
  string_type: '문자열이어야 하는 항목의 타입이 다릅니다.',
  missing_field: '필수 필드가 응답에서 빠졌습니다.',
  unexpected_fields: '허용하지 않은 필드가 응답에 포함됐습니다.',
  list_type_or_limit: '목록 형식이 아니거나 허용된 항목 수를 넘었습니다.',
  empty_text: '필수 설명이 비어 있습니다.',
  text_limit: '설명이 800자 제한을 넘었습니다.',
  item_limit: '허용된 항목 수를 넘었습니다.',
  invalid_or_duplicate_id: '해석 ID가 비어 있거나 문자열이 아니거나 다른 항목과 중복됩니다.',
  invalid_enum: '허용된 상태·유형 값이 아닙니다.',
  unknown_reference: '이 단계에 허용된 근거·항목 ID가 아닌 값을 참조했습니다.',
  missing_support: '필수 근거 참조가 없습니다. 근거 없는 미확인 항목에는 이유가 필요합니다.',
  criterion_count: 'method=llm인 Runbook 기준마다 정확히 한 개의 판단을 반환해야 합니다.',
  unknown_or_duplicate_criterion:
    'Runbook 기준의 전체 key와 일치하지 않거나 같은 기준을 중복 답했습니다. 짧은 id는 사용할 수 없습니다.',
  draft_mismatch: '요청한 초안의 식별값과 응답의 식별값이 다릅니다.',
  rubric_mismatch: '척도별 판정과 최종 검토 판정이 서로 맞지 않습니다.',
  issue_verdict_mismatch:
    '수정 필요 판정에는 지적 사항이 필요하고, 통과 판정에는 지적 사항이 없어야 합니다.',
  query_count: '추가 확인 질문에는 허용된 조회를 1~3개 지정해야 합니다.',
  selection_shape: '조회 선택 응답에는 query_ids 목록 또는 기존 query_id 형식만 허용됩니다.',
  json_syntax: '응답을 JSON으로 읽지 못했습니다. 내부 필드 검증 이전의 실패입니다.',
  unexpected_value_type: '예상하지 않은 값 타입으로 검증을 완료하지 못했습니다.',
  author_shape: '통합 응답의 최상위 JSON 구조가 맞지 않습니다.',
  interpretation_invalid: '증거 해석의 형식 또는 근거 참조가 맞지 않습니다.',
  interpretation_dependency: '증거 해석이 검증되지 않아 원인 분석을 채택할 수 없습니다.',
  finding_dependency: '이 응답의 해석 항목을 참조해야 하지만 참조가 없거나 잘못됐습니다.',
  invalid_hypotheses: '원인 후보는 최대 8개인 목록이어야 합니다.',
  invalid_hypothesis_shape: '원인 후보에 필요한 항목이 빠졌거나 허용하지 않은 항목이 있습니다.',
  invalid_claim: '원인 후보 문장이 비어 있거나 문자열이 아니거나 길이 제한을 넘었습니다.',
  invalid_hypothesis_references: '근거 참조 또는 추가 확인 목록의 형식·길이가 맞지 않습니다.',
  invalid_evidence_references: '원인 후보의 근거 참조가 허용된 관측과 맞지 않습니다.',
  empty_supporting_refs: '원인 후보를 뒷받침하는 관측 근거가 없습니다.',
  unknown_observation_refs: '허용된 관측 근거에 없는 ID를 인용했습니다.',
  overlapping_evidence_refs: '같은 근거를 지지 근거와 반대 근거에 중복 사용했습니다.',
  identity_is_not_cause: '장치 연결의 불확실성을 장애 원인으로 제시해 코드 검증에서 제외했습니다.',
  unresolved_device_mechanism:
    '대상 장치가 미확정인 근거로 구체적인 고장 원인을 제시해 코드 검증에서 제외했습니다.',
  numeric: '코드의 수치 표현 검사에서 허용되지 않은 표현을 발견했습니다.',
  non_korean: '코드의 한국어 표현 검사에서 허용되지 않은 표현을 발견했습니다.',
  precision_loss: '입력에 확인되지 않은 시각 정밀도 손실을 주장했습니다.',
  assertion: '코드의 단정 표현 검사에 걸렸습니다. 품질 검토의 판정과는 별개입니다.',
  invalid_limitations: '분석 한계 목록의 형식·길이가 맞지 않습니다.',
  invalid_analysis_value: '분석 항목을 읽는 중 예상하지 않은 값 형식을 발견했습니다.',
};

export function RcaModelFailure({ diagnostic }: { diagnostic: Row }) {
  const code = str(diagnostic.error_code ?? diagnostic.failure_reason ?? diagnostic.reason);
  if (!code) return null;
  const failures: Record<string, [string, string]> = {
    invalid_author_response: [
      '응답 수신 · 통합 분석 검증 실패',
      '모델이 답했지만 요구한 형식·근거 참조 검사를 통과하지 못했습니다. 연결 실패가 아닙니다. 채택 여부는 아래 기록을 확인하세요.',
    ],
    invalid_stage_output: [
      '응답 수신 · 단계 검증 실패',
      '응답을 받았지만 해당 단계의 형식·근거 검사를 통과하지 못했습니다.',
    ],
    invalid_model_response: [
      '응답 수신 · 분석 검증 실패',
      '응답을 받았지만 분석 결과로 사용할 수 있는 형식이 아닙니다.',
    ],
    llm_invalid_output: [
      '응답 수신 · JSON 해석 실패',
      '모델 응답을 JSON으로 읽지 못했습니다. 연결 실패가 아닙니다.',
    ],
    llm_output_truncated: [
      '응답 수신 · 출력 잘림',
      '출력 한도에 도달해 응답이 잘렸습니다. 완성된 분석으로 채택하지 않았습니다.',
    ],
    llm_http_error: [
      '모델 요청 실패 · HTTP 오류',
      '서버가 오류 응답을 반환했습니다. 모델 분석 응답의 내용 검증까지 진행하지 못했습니다. 이 코드만으로 연결 불가나 인증 실패를 단정할 수 없습니다.',
    ],
    llm_no_response: [
      '유효한 응답 없음 · 원인 미확인',
      '연결 실패인지 응답 처리 문제인지는 이 기록만으로 확정할 수 없습니다.',
    ],
    model_not_configured: ['호출 전 생략 · 모델 미설정', '모델 설정이 없어 요청하지 않았습니다.'],
    llm_input_size_exceeded: [
      '호출 전 생략 · 입력 크기 초과',
      '해당 요청은 입력 크기 검사에서 차단됐습니다. 앞선 요청 기록과 구분하세요.',
    ],
    llm_token_budget_exhausted: [
      '호출 전 생략 · 토큰 예산 부족',
      '해당 요청에 필요한 예산이 부족합니다. 앞선 요청의 응답 유무와는 별개입니다.',
    ],
    llm_context_budget_exhausted: [
      '호출 전 생략 · 분석 입력 구성 불가',
      '입력 한도 또는 관측 근거 부재로 분석 요청을 생략했습니다. 구 기록의 두 원인은 이 코드만으로 구분할 수 없습니다.',
    ],
    llm_deadline_exhausted: [
      '요청 실행 기한 소진',
      '남은 실행 시간이 없습니다. 이 코드만으로 연결 실패를 단정할 수 없습니다.',
    ],
  };
  const failure = failures[code];
  return (
    <section aria-label="모델 호출과 응답 검증 구분">
      <strong>{failure?.[0] ?? '실패 유형 미분류 · 저장 사유 확인'}</strong>
      <p>{failure?.[1] ?? '이 사유만으로 연결 실패나 응답 검증 실패를 추정하지 않습니다.'}</p>
      <p>
        저장 사유: <code>{code}</code>
      </p>
      {diagnostic.adoption != null && (
        <p>
          응답 채택:{' '}
          {(
            {
              none: '해석·분석 모두 미채택',
              interpretation_only: '증거 해석만 보존 · 원인 분석 미채택',
              validated_response: '검증된 응답 채택',
            } as Record<string, string>
          )[str(diagnostic.adoption)] ?? '미확인'}
        </p>
      )}
      <RcaValidationDetails diagnostic={diagnostic} />
    </section>
  );
}

function validationLocation(detail: Row): string {
  const path = str(detail.path);
  const rootFields: Record<string, string> = {
    analysis_id: '검토 대상 초안',
    verdict: '최종 검토 판정',
    query_id: '선택 조회',
    query_ids: '선택 조회',
  };
  const rootField = path.match(/^\$\.(analysis_id|verdict|query_ids?)(?:\[(\d+)\])?$/);
  if (rootField)
    return (
      rootFields[rootField[1]] + (rootField[2] == null ? '' : ' ' + (Number(rootField[2]) + 1))
    );
  const sections: Record<string, string> = {
    findings: '해석',
    unknowns: '미확인',
    conflicts: '상충',
    limitations: '한계',
    criterion_assessments: 'Runbook 판단 기준',
    issues: '검토 지적',
    followup_questions: '추가 확인 질문',
  };
  const fields: Record<string, string> = {
    statement: '설명',
    reason: '이유',
    evidence_refs: '근거 참조',
    finding_refs: '해석 연결',
    criterion_id: '판단 기준 ID',
    kind: '보고·추론 구분',
    status: '판정',
    id: '해석 ID',
    query_ids: '조회 ID',
    suggested_resolution: '수정 제안',
    claim_id: '주장 ID',
    expected_effect: '기대 효과',
    question: '질문',
  };
  const item = path.match(
    /^\$(?:\.interpretation)?\.(findings|unknowns|conflicts|limitations|criterion_assessments|issues|followup_questions)(?:\[(\d+)\])?(?:\.(\w+))?(?:\[(\d+)\])?$/,
  );
  if (item)
    return `${sections[item[1]]}${item[2] == null ? '' : ` ${Number(item[2]) + 1}`}${item[3] ? ` · ${fields[item[3]] ?? '필드'}` : ''}${item[4] == null ? '' : ` ${Number(item[4]) + 1}`}`;
  const criterion = path.match(/^\$\.criteria\.(\w+)(?:\.(\w+))?(?:\[(\d+)\])?$/);
  if (criterion)
    return `검토 척도 · ${label(criterion[1])}${criterion[2] ? ` · ${fields[criterion[2]] ?? '필드'}` : ''}${criterion[3] == null ? '' : ` ${Number(criterion[3]) + 1}`}`;
  return typeof detail.hypothesis_index === 'number'
    ? `원인 후보 ${detail.hypothesis_index + 1}`
    : typeof detail.limitation_index === 'number'
      ? `분석 한계 ${detail.limitation_index + 1}`
      : '응답 구조';
}

export function RcaValidationDetails({ diagnostic }: { diagnostic: Row }) {
  const reasons: Record<string, string> = {
    author_shape:
      '통합 응답의 최상위 구조가 다릅니다. interpretation(증거 해석), hypotheses(원인 후보), limitations(분석 한계)만 가진 JSON 객체가 필요합니다. 실제 누락·추가 항목은 이 기록에 저장되지 않았습니다.',
    interpretation_invalid: '증거 해석의 형식 또는 근거 참조 검증에 실패했습니다.',
    analysis_invalid: '원인 분석의 형식·근거 참조 또는 해석과의 연결 검증에 실패했습니다.',
  };
  return (
    <>
      {[...rows(diagnostic.validation_failures), ...rows(diagnostic.validation_details)]
        .filter((attempt) => Object.keys(attempt).length > 0)
        .map((attempt, i) => (
          <div key={i}>
            {typeof attempt.attempt === 'number' && <p>{attempt.attempt}차 응답 검증</p>}
            {rows(attempt.details).length ? (
              rows(attempt.details).map((detail, j) => (
                <div key={j}>
                  <p>
                    <strong>{validationLocation(detail)}: </strong>
                    {validationMeaning[str(detail.rule)] ??
                      validationMeaning[str(detail.code)] ??
                      '설명 미등록 · 세부 진단을 확인하세요.'}
                  </p>
                  <details>
                    <summary>검증 위치·코드</summary>
                    <p>
                      위치: <code>{str(detail.path, '미기록')}</code>
                    </p>
                    <p>
                      검증 코드: <code>{str(detail.code)}</code> · 규칙:{' '}
                      <code>{str(detail.rule)}</code>
                    </p>
                    <p>
                      항목 번호는 응답 목록 순서입니다. 첫 검증 실패를 기록하며 거절된 원문은
                      저장하지 않습니다.
                    </p>
                  </details>
                </div>
              ))
            ) : (
              <>
                {strings(attempt.reasons).map((reason) => (
                  <p key={reason}>{reasons[reason] ?? '검증 사유 설명 미등록'}</p>
                ))}
                <p>이 기록에는 세부 검증 위치·사유가 저장되지 않았습니다.</p>
              </>
            )}
          </div>
        ))}
    </>
  );
}

function RequestChecks({ value }: { value: unknown }) {
  const checks = rows(value);
  if (!checks.length) return <p>요청 크기·예산 사전 검사: 기록 없음</p>;
  return (
    <details>
      <summary>요청 크기·예산 사전 검사</summary>
      <p>
        토큰 필요량은 입력 바이트 기준의 보수적 계산이며 실제 사용량이 아닙니다. 출력 상한은 전송 시
        최초 적용할 계산값입니다. 생략된 요청에는 적용되지 않았습니다.
      </p>
      {checks.map((check, i) => (
        <div key={i}>
          <h4>{i + 1}차 요청 확인</h4>
          <p>
            입력 크기:{' '}
            {check.input_size_exceeded === true
              ? '상한 초과'
              : check.input_size_exceeded === false
                ? '상한 이내'
                : '기록 없음'}
            {' · '}토큰 예산:{' '}
            {check.token_budget_exhausted === true
              ? '부족'
              : check.token_budget_exhausted === false
                ? '사전 검사 충족'
                : '기록 없음'}
            {' · '}
            {check.model_called === true
              ? '논리 모델 요청 실행'
              : check.model_called === false
                ? '모델 호출 전 생략'
                : '호출 여부 미확인'}
          </p>
          <dl className="details">
            <dt>요청 본문 / 크기 상한 (바이트)</dt>
            <dd>
              {amount(check.input_bytes)} / {amount(check.max_input_bytes)}
            </dd>
            <dt>남은 전체 / 예약 / 사용 가능 예산 (토큰)</dt>
            <dd>
              {amount(check.remaining_tokens)} / {amount(check.reserved_tokens)} /{' '}
              {amount(check.available_tokens)}
            </dd>
            <dt>사전 검사 필요량 (토큰, 보수적 계산)</dt>
            <dd>{amount(check.required_tokens)} 초과 필요</dd>
            <dt>최초 출력 상한 (토큰, 계산값)</dt>
            <dd>{amount(check.output_token_cap)}</dd>
          </dl>
        </div>
      ))}
    </details>
  );
}

function StageUsage({ value }: { value: unknown }) {
  const usage = obj(value);
  if (typeof usage.request_attempts !== 'number') return null;
  return (
    <p>
      전송 시도 {amount(usage.request_attempts)}회 · 모델 보고 토큰 {amount(usage.total_tokens)}
      {typeof usage.charged_tokens === 'number' && (
        <>
          {' '}
          · 예산 차감 {amount(usage.charged_tokens)}토큰 (미보고 응답{' '}
          {amount(usage.usage_missing_calls)}건의 보수적 차감 {amount(usage.estimated_tokens)}토큰
          포함)
        </>
      )}
    </p>
  );
}

export function RcaEvaluationTrace({
  items,
  onEvidence,
}: {
  items: Row[];
  onEvidence: (id: string) => void;
}) {
  const stages = items.filter((r) => rcaStages[str(r.query_id)]);
  if (!stages.length) return null;
  return (
    <section aria-label="RCA 처리 흐름">
      <h3>RCA 처리 흐름</h3>
      <p>
        현재 불러온 기록 순서입니다. LLM 표시는 단계의 담당이며 실제 호출 여부는 호출 횟수·실행
        상태로 확인하세요. D 번호는 조회 식별자이며 실행 순번이 아닙니다.
      </p>
      <ol>
        {stages.map((record) => {
          const meta = obj(record.quality);
          const body = obj(record.snapshot);
          const step = stageForRecord(record);
          const round = meta.round ?? body.round;
          const status = meta.execution_status ?? body.execution_status ?? body.status;
          return (
            <li key={str(record.id)} className="data-item">
              <button className="text-link" onClick={() => onEvidence(str(record.id))}>
                {typeof round === 'number' ? `${round + 1}회차 · ` : ''}
                {step.title} · {step.actor}
              </button>
              <p>{step.purpose}</p>
              <p>
                {status ? label(status) : '기록됨'}
                {meta.verdict ? ` · ${label(meta.verdict)}` : ''}
                {meta.reason ? ` · ${label(meta.reason)}` : ''}
                {meta.failure_reason ? ` · 재검토 실패: ${label(meta.failure_reason)}` : ''}
              </p>
              {typeof meta.attempts === 'number' && (
                <p>
                  논리 모델 요청 {meta.attempts}회{meta.model ? ` · ${str(meta.model)}` : ''}
                </p>
              )}
              <StageUsage value={meta.usage} />
              {['evidence_interpretation', 'analysis_review', 'report_assembly'].includes(
                str(record.query_id),
              ) && <RequestChecks value={meta.request_checks} />}
              {meta.started_at != null && (
                <p>
                  시작 {str(meta.started_at)} → 완료 {str(meta.completed_at, '미확인')}
                  {typeof meta.elapsed_seconds === 'number' ? ` · ${meta.elapsed_seconds}초` : ''}
                </p>
              )}
              {meta.action != null && (
                <p>
                  결정:{' '}
                  {(
                    {
                      revise: '분석 수정',
                      collect: '추가 수집',
                      finish: '종료',
                      withhold: '문제 주장 보류',
                      reuse: '기존 분석 유지',
                    } as Record<string, string>
                  )[str(meta.action)] || str(meta.action)}
                </p>
              )}
              {meta.analysis_id != null && (
                <details>
                  <summary>대상 초안 ID</summary>
                  <code>{str(meta.analysis_id)}</code>
                </details>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function RcaStageDetails({
  record,
  onEvidence,
  compact = false,
}: {
  record: Row;
  onEvidence?: (id: string) => void;
  compact?: boolean;
}) {
  const step = stageForRecord(record);
  if (!step) return null;
  const body = obj(record.snapshot);
  const interpretation = obj(body.interpretation);
  const review = obj(body.review);
  const synthesis = obj(body.diagnostics);
  const allocation = obj(synthesis.budget_allocation);
  if (
    record.query_id === 'analysis_review' &&
    body.execution_status === 'skipped' &&
    body.reason === 'draft_changed_after_review' &&
    body.attempts === 0 &&
    !body.failure_reason &&
    !(Number(obj(body.usage).request_attempts) > 0 || Number(obj(body.usage).calls) > 0)
  )
    return (
      <section aria-label="평가 단계 상세">
        {!compact && (
          <>
            <h3>{step.title}</h3>
            <p>{step.purpose}</p>
          </>
        )}
        <p>LLM 호출 없음</p>
        {typeof body.previous_review_evidence_id === 'string' && onEvidence && (
          <button
            className="text-link"
            onClick={() => onEvidence(body.previous_review_evidence_id as string)}
          >
            이전 검토 지적 확인
          </button>
        )}
      </section>
    );
  const refs = (value: unknown) => (
    <span>
      {strings(value).map((id) =>
        onEvidence ? (
          <button className="text-link" key={id} onClick={() => onEvidence(id)}>
            {id}
          </button>
        ) : (
          <code key={id}>{id} </code>
        ),
      )}
    </span>
  );
  return (
    <section aria-label="평가 단계 상세">
      {!compact && (
        <>
          <h3>
            {step.title} · {step.actor}
          </h3>
          <p>{step.purpose}</p>
        </>
      )}
      {record.query_id === 'rca_result_frozen' && (
        <p>
          RCA 근거 자료 식별값: <code>{str(body.material_hash, '미기록')}</code>. 이후 보고서
          작성에서 이 자료가 바뀌면 결과 공개를 중단합니다.
        </p>
      )}
      {record.query_id === 'report_assembly' && (
        <p>
          작성 방식:{' '}
          {obj(body.report).method === 'llm_composed'
            ? '고정된 RCA 자료를 보고서 LLM이 서술'
            : obj(body.report).method === 'llm_prioritized'
              ? '확정된 문장을 LLM이 정렬'
              : obj(body.report).method === 'deterministic_fallback'
                ? '코드의 기본 순서로 작성'
                : '미기록'}
          . 저장된 RCA 판정은 유지합니다. 보고서 문장의 의미 일치 여부는 연결된 원문과 대조할 수
          있습니다.
          {obj(body.report).fallback_reason != null && (
            <> 기본 순서 사용 이유: {label(obj(body.report).fallback_reason)}.</>
          )}
        </p>
      )}
      {['evidence_interpretation', 'rca_synthesis', 'analysis_review', 'report_assembly'].includes(
        str(record.query_id),
      ) && (
        <p>
          {modelExecution(
            record.query_id === 'rca_synthesis' ? { ...synthesis, usage: body.usage } : body,
          )}
        </p>
      )}
      {record.query_id === 'rca_synthesis' && (
        <>
          {body.generation_mode === 'combined' && (
            <RequestChecks value={rows(synthesis.requests).map((row) => row.request_check)} />
          )}
          {synthesis.error_code != null && <RcaModelFailure diagnostic={synthesis} />}
          <p>
            분석 입력 크기: {amount(synthesis.input_bytes)} / 축약 전{' '}
            {amount(synthesis.original_input_bytes)} 바이트
          </p>
          <p>
            선택된 관측 근거:{' '}
            {Array.isArray(synthesis.input_evidence_refs)
              ? strings(synthesis.input_evidence_refs).length
                ? refs(synthesis.input_evidence_refs)
                : '없음 (빈 목록 기록)'
              : '미기록'}
          </p>
          <p>
            선택된 근거는 모델 전송 완료와 별개입니다. 입력 제한과 관측 부재가 같은 코드로 기록된 구
            결과의 세부 원인은 추정하지 않습니다.
          </p>
          {Object.keys(allocation).length > 0 && (
            <details>
              <summary>분석·검토 예산 배분</summary>
              <p>
                검토 예약 요청 {amount(allocation.requested_review_reserve)} → 적용{' '}
                {amount(allocation.applied_review_reserve)} 토큰
              </p>
              <p>
                남은 전체 예산: {amount(allocation.remaining_tokens)} · 검토 보호 하한:{' '}
                {amount(allocation.review_floor_tokens)} 토큰
              </p>
              <p>
                조정 사유:{' '}
                {(
                  {
                    reservation_unchanged: '기존 예약 유지',
                    analysis_input_preserved:
                      '분석에 쓸 근거를 담기 위해 검토 예약의 일부를 분석에 배정했습니다.',
                    analysis_review_budget_insufficient: '분석과 검토를 함께 감당할 예산 부족',
                  } as Record<string, string>
                )[str(allocation.reason)] || str(allocation.reason, '미기록')}
              </p>
              <p>
                하한은 규칙 초안·검토 입력·기본 출력 상한을 기준으로 합니다. 이후 모델이 추가한
                주장이나 재시도 비용까지 보장하지 않습니다. 구 기록에 없는 하한은 추정하지 않습니다.
              </p>
            </details>
          )}
        </>
      )}
      {!compact && body.execution_status != null && (
        <p>{reviewStatus(record) ?? label(body.execution_status)}</p>
      )}
      {body.reason != null && (
        <p>
          사유: {label(body.reason)} <code>{str(body.reason)}</code>
        </p>
      )}
      {body.failure_reason != null && (
        <p>
          재검토 실패: {label(body.failure_reason)} <code>{str(body.failure_reason)}</code>
        </p>
      )}
      {['evidence_interpretation', 'analysis_review', 'report_assembly'].includes(
        str(record.query_id),
      ) &&
        (body.failure_reason != null || body.execution_status === 'failed') && (
          <RcaModelFailure diagnostic={body} />
        )}
      {['evidence_interpretation', 'analysis_review', 'report_assembly'].includes(
        str(record.query_id),
      ) && <RequestChecks value={body.request_checks} />}
      {body.execution_status === 'complete' && rows(body.validation_details).length > 0 && (
        <details>
          <summary>이전 응답의 검증·수정 이력</summary>
          <RcaValidationDetails diagnostic={body} />
        </details>
      )}
      {record.query_id === 'report_assembly' &&
        obj(body.report).presentation === 'rca-material/1' && (
          <>
            <p>
              결과 저장 준비: {body.assembly_status === 'complete' ? '완료' : '미기록'} · 보고서
              호출 상태와 RCA 품질 판정은 별개입니다.
            </p>
            <p>조사 종료 이유: {label(body.stop_reason)}</p>
            <details>
              <summary>보고서에 전달한 RCA 자료 · 원문 대조</summary>
              {rows(obj(body.report).source_items).map((item) => (
                <p key={str(item.id)}>
                  <code>{str(item.id)}</code> {str(item.text)} {refs(item.evidence_refs)}
                </p>
              ))}
            </details>
          </>
        )}
      <StageUsage value={body.usage} />
      {body.analysis_id != null && (
        <details>
          <summary>검토 대상 식별값</summary>
          <code>{str(body.analysis_id)}</code>
        </details>
      )}
      {Object.entries({
        findings: '관측 보고·추론',
        unknowns: '아직 모르는 내용',
        conflicts: '상충하는 정보',
        limitations: '해석의 한계',
      }).map(
        ([key, title]) =>
          rows(interpretation[key]).length > 0 && (
            <div key={key}>
              <h4>{title}</h4>
              <ul>
                {rows(interpretation[key]).map((row, i) => (
                  <li key={i}>
                    {row.kind === 'inferred'
                      ? '추론: '
                      : row.kind === 'observed'
                        ? '원문 보고: '
                        : ''}
                    {str(row.statement)} {refs(row.evidence_refs)}
                  </li>
                ))}
              </ul>
            </div>
          ),
      )}
      {rows(body.checks).length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>검사</th>
                <th>결과</th>
                <th>이유·근거</th>
              </tr>
            </thead>
            <tbody>
              {rows(body.checks).map((row, i) => (
                <tr key={i}>
                  <td>{str(row.check)}</td>
                  <td>{label(row.outcome)}</td>
                  <td>
                    {str(row.reason)} {refs(row.evidence_refs)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {Object.keys(obj(review.criteria)).length > 0 && (
        <>
          <h4>평가 척도 · 버전 {str(body.rubric_version, '1')}</h4>
          <p>판정: {label(review.verdict)}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>항목</th>
                  <th>판정</th>
                  <th>이유·근거</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(obj(review.criteria)).map(([key, value]) => {
                  const row = obj(value);
                  return (
                    <tr key={key}>
                      <th>{label(key)}</th>
                      <td>{label(row.status)}</td>
                      <td>
                        {str(row.reason)} {refs(row.evidence_refs)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {rows(review.issues).map((issue, i) => (
        <p key={i}>
          수정 대상 {str(issue.claim_id, '초안 전체')}: {str(issue.reason)} →{' '}
          {str(issue.suggested_resolution)} {refs(issue.evidence_refs)}
        </p>
      ))}
      {rows(review.followup_questions).map((question, i) => (
        <p key={i}>
          추가 확인: {str(question.question)} · 기대 효과: {str(question.expected_effect)} · 제안
          조회: {strings(question.query_ids).join(', ')} (실제 실행 결정과 구분)
        </p>
      ))}
      {rows(body.claims).map((claim) => (
        <p key={str(claim.id)}>
          <strong>
            {claim.source === 'runbook'
              ? '조사 지침에서 가져온 주장'
              : claim.source === 'analysis'
                ? '분석에서 작성한 주장'
                : '출처 종류 미확인'}
          </strong>
          : {str(claim.statement)} {refs(claim.supporting_refs)}
        </p>
      ))}
      {rows(body.hypotheses).map((candidate, i) => (
        <p key={i}>
          원인 후보: {str(candidate.claim, '설명 미기록')} {refs(candidate.supporting_refs)}
        </p>
      ))}
      {body.action != null && (
        <p>
          다음 행동: {str(body.action)} · 이유: {label(body.reason)} · 선택한 조회:{' '}
          {strings(body.selected_queries).join(', ') || '없음'}
        </p>
      )}
      {strings(body.input_evidence_refs).length > 0 && (
        <p>실제 입력 근거: {refs(body.input_evidence_refs)}</p>
      )}
      {obj(body.context_selection).complete === false && (
        <p>모델 입력에서 일부 자료가 생략됐습니다. 원본 전체를 검토했다는 뜻이 아닙니다.</p>
      )}
    </section>
  );
}
