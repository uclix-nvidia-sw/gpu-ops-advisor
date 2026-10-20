import { obj, rows, str, strings, type Row } from '../lib/live';

export const evaluationLabels: Record<string, string> = {
  complete: '완료',
  no_new_evidence: '새 관측 없음 · 같은 증거의 분석 재호출 생략',
  same_evidence_rewrite_blocked: '같은 증거의 재작성 금지 · 검토 지적 보존',
  goal_achieved: '조사 목적 달성으로 종료',
  goal_not_met: '목적 미달 · 가능한 보완 없음',
  achieved: '조사 목적 달성',
  not_achieved: '조사 목적 미달',
  satisfied: '충족',
  not_satisfied: '불충족',
  review_rejected_interpretation: '검토에서 지적된 해석 제외',
  invalid_author_response: '통합 작성 응답 검증 실패',
  no_remaining_queries: '허용된 미수행 조회 없음',
  authorized_followup: '조건을 충족한 보완 조회',
  review_revision_required: '검토 지적에 따른 분석 수정',
  unknown: '미확인',
  fail: '검사 불일치',
  partial: '부분 수집',
  failed: '실패',
  not_requested: '수집 불필요',
  skipped: '생략',
  acceptable: '근거 범위에서 타당',
  acceptable_after_feedback: '지적 주장 제외 후 근거 범위에서 타당',
  revision_required: '수정 필요',
  undetermined: '판단 불가',
  pass: '충족',
  needs_revision: '수정 필요',
  not_applicable: '해당 없음',
  grounding: '근거와 결론의 연결',
  identity_time: '대상·시각의 구분',
  contradictions: '반대 근거·모순',
  alternatives: '중요한 대안',
  limitations: '수집·해석 한계 설명',
  evidence_use: '중요한 증거 활용',
  review_accepted: '분석 검토 통과',
  no_available_followup: '허용된 미수행 조회 없음',
  followup_not_selected: '추가 조회 미선택',
  selection_conditions_missing: '추가 조회 선택 조건 없음',
  query_budget_exhausted: '조회 예산 소진',
  llm_budget_exhausted: 'LLM 예산 소진',
  round_limit_reached: '수집 라운드 한도',
  revision_limit_reached: '수정 횟수 한도',
  analysis_unresolved: '분석 미해결',
  no_usable_evidence: '해석 가능한 증거 없음',
  model_unavailable: '모델 사용 불가',
  model_not_configured: '모델 미설정',
  llm_input_size_exceeded: '모델 입력 크기 상한 초과',
  llm_token_budget_exhausted: '남은 모델 토큰 예산 부족',
  llm_http_error: '모델 서버 HTTP 오류',
  llm_deadline_exhausted: '모델 요청 실행 기한 소진',
  llm_output_truncated: '모델 출력 잘림',
  llm_invalid_output: '모델 응답 형식 오류',
  invalid_stage_output: '단계 출력 검증 실패',
  llm_no_response: '유효한 모델 응답 없음',
  fast_path: '기존 규칙 경로',
  alert_match: '알람·D09 일치로 분석·검토 생략',
  draft_changed_after_review: '검토 후 변경된 최종 초안은 미검토',
};

export function RcaEvaluation({ result }: { result: Row }) {
  const evaluation = obj(obj(result.quality).rca_evaluation);
  const label = (value: unknown) => evaluationLabels[str(value)] || str(value, '미확인');
  if (!Object.keys(evaluation).length)
    return <p>이전 결과: 분리된 분석 품질 검토 기록이 없습니다.</p>;
  if (!['1', '2'].includes(str(evaluation.schema_version)))
    return <p>지원하지 않는 평가 형식입니다. 원본 기록을 확인하세요.</p>;
  const collection = obj(evaluation.collection);
  const evidence = obj(evaluation.evidence);
  const review = obj(evaluation.review);
  const investigation = obj(evaluation.investigation);
  const reviewed =
    review.execution_status === 'complete' && review.analysis_id === evaluation.analysis_id;
  return (
    <section aria-label="RCA 평가 구분">
      <h4>수집·증거 해석·분석 품질</h4>
      {evaluation.generation_mode === 'combined' && (
        <p>증거 해석·RCA 분석을 작성 LLM이 함께 처리하고, 별도 검토 LLM이 품질을 확인합니다.</p>
      )}
      <RcaObjective
        value={{
          ...obj(investigation.objective),
          ...(obj(investigation.objective).status === 'achieved' &&
          (!reviewed ||
            !['acceptable', 'acceptable_after_feedback'].includes(String(review.verdict)) ||
            obj(investigation.objective).analysis_id !== evaluation.analysis_id)
            ? { status: 'unknown' }
            : {}),
        }}
      />
      <dl className="details">
        <dt>수집 상태</dt>
        <dd>{label(collection.status)}</dd>
        <dt>증거 해석 실행</dt>
        <dd>
          {label(evidence.execution_status)}
          {evidence.reason ? ` · ${label(evidence.reason)}` : ''}
        </dd>
        <dt>분석 품질</dt>
        <dd>
          {reviewed ? label(review.verdict) : '미검토'}
          {review.reason ? ` · ${label(review.reason)}` : ''}
          {review.failure_reason ? ` · 재검토 실패: ${label(review.failure_reason)}` : ''}
        </dd>
        <dt>조사 진행</dt>
        <dd>
          {investigation.status === 'finished' ? '종료' : '미확인'} ·{' '}
          {label(investigation.stop_reason)}
        </dd>
      </dl>
      <p>해석 완료는 모든 사실의 확인을, 검토 통과와 조사 종료는 원인 확정을 뜻하지 않습니다.</p>
      {!reviewed && (
        <p>
          미검토는 최종 초안의 상태입니다. 실제 요청·응답과 실패 이유는 개발측 ‘워크플로우 디버깅’의
          분석 품질 검토 기록에서 확인하세요.
        </p>
      )}
      {reviewed && (
        <details>
          <summary>평가 척도·항목별 판단 근거</summary>
          <p>
            척도 버전 {str(review.rubric_version, '미확인')} · 점수 합산 없이 항목별 문제와 판단
            한계를 검토합니다.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>항목</th>
                  <th>판정</th>
                  <th>이유·근거 ID</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(obj(review.criteria)).map(([key, value]) => {
                  const criterion = obj(value);
                  return (
                    <tr key={key}>
                      <th>{label(key)}</th>
                      <td>{label(criterion.status)}</td>
                      <td>
                        {str(criterion.reason)}
                        <br />
                        {Array.isArray(criterion.evidence_refs)
                          ? criterion.evidence_refs.join(', ')
                          : ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <details>
        <summary>평가 대상·추적 ID</summary>
        <code className="record-key">{str(evaluation.analysis_id)}</code>
        <p>
          원본 증거, 해석, 초안, 검토, 다음 행동의 연결은 작업 디버깅의 증거 기록에서 확인할 수
          있습니다.
        </p>
      </details>
    </section>
  );
}

export function RcaObjective({ value }: { value: unknown }) {
  const objective = obj(value);
  if (!rows(objective.policies).length) return null;
  return (
    <section aria-label="조사 목적과 완료 기준">
      <h4>{evaluationLabels[str(objective.status)] || '조사 기준 확인 중'}</h4>
      {objective.status === 'achieved' && (
        <p>
          대상·기간의 오류 보고와 해석의 한계를 확인했고, 같은 분석본의 품질 검토도 통과했습니다.
          Runbook의 조사 목적을 충족했으므로 선택 조회가 남아 있어도 추가 수집 없이 종료합니다.
        </p>
      )}
      <p>
        목적 달성과 근본 원인 확정은 다릅니다. 아래 필수 기준과 같은 최종 초안의 품질 검토가 모두
        충족되어야 목적 달성으로 종료합니다.
      </p>
      {rows(objective.policies).map((policy) => (
        <div key={str(policy.runbook_revision_id)}>
          <p>
            <strong>{str(obj(policy.goal).question)}</strong>
          </p>
          <p>{str(obj(policy.goal).conclusion_scope)}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>확인할 내용</th>
                  <th>필수 여부</th>
                  <th>판단</th>
                  <th>담당·근거</th>
                </tr>
              </thead>
              <tbody>
                {rows(policy.criteria).map((row) => (
                  <tr key={str(row.key)}>
                    <td>{str(row.question)}</td>
                    <td>{row.required ? '필수' : '선택'}</td>
                    <td>{evaluationLabels[str(row.status)] || '미확정'}</td>
                    <td>
                      {row.method === 'code'
                        ? '코드의 명확한 조건 검사'
                        : '작성 LLM 제안 + 별도 품질 검토'}
                      <details>
                        <summary>근거 ID</summary>
                        {Array.isArray(row.evidence_refs)
                          ? row.evidence_refs.join(', ')
                          : '기록 없음'}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows(policy.blocking_conditions).some((row) => row.status !== 'satisfied') && (
            <p>
              대상·기간·신원·필수 수집에 미확정 또는 충돌이 있어 종료 기준을 충족하지 못했습니다.
            </p>
          )}
          <p>
            필수 근거 미확인:{' '}
            {Array.isArray(policy.unmet_required_evidence) && policy.unmet_required_evidence.length
              ? policy.unmet_required_evidence.join(', ')
              : '없음'}
          </p>
          <p>
            남아 있어도 이 목적을 막지 않는 미확인:{' '}
            {Array.isArray(policy.non_blocking_unknowns)
              ? policy.non_blocking_unknowns
                  .map(
                    (item) =>
                      (
                        ({
                          causal_confirmation_evidence: '근본 원인',
                          current_health: '현재 장치 상태',
                          physical_or_synthetic_origin: '실제 오류 또는 시험 주입 여부',
                        }) as Record<string, string>
                      )[str(item)] || str(item),
                  )
                  .join(', ')
              : '기록 없음'}
          </p>
          <details>
            <summary>판단 기준의 Runbook 출처</summary>
            <p>
              {str(policy.runbook_revision_id)} · {str(policy.content_hash)}
            </p>
          </details>
        </div>
      ))}
    </section>
  );
}

export function RcaDecisionSummary({ value }: { value: unknown }) {
  const decision = obj(value);
  const collected = strings(decision.collected_queries);
  const deferred = strings(decision.deferred_queries);
  return (
    <>
      {decision.decision_policy_status === 'not_configured' && (
        <p>
          이 작업이 사용한 Runbook에는 조사 목적에 따른 종료 기준이 없습니다. 품질 검토를 통과해도
          기존 보완 조회 규칙에 따라 수집이 이어질 수 있습니다. 종료 기준을 적용하려면
          decision_policy가 있는 Runbook 1.1을 새 revision으로 발행해야 합니다. 코드 배포만으로
          발행된 지침이 바뀌지는 않습니다.
        </p>
      )}
      {decision.decision_policy_status === 'mixed' && (
        <p>
          일부 조사 지침에 종료 기준이 없거나 조사 범위가 확장되어 목적 달성 종료를 적용하지
          못했습니다.
        </p>
      )}
      {(decision.reason === 'goal_achieved' || decision.stop_reason === 'goal_achieved') && (
        <>
          {collected.length > 0 && <p>목표 확인에 사용한 수집: {collected.join(', ')}</p>}
          {deferred.length > 0 && (
            <p>목표를 충족해 추가로 수집하지 않은 선택 조회: {deferred.join(', ')}</p>
          )}
        </>
      )}
    </>
  );
}
