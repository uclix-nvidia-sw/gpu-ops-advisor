import { obj, str, type Row } from '../lib/live';

export const evaluationLabels: Record<string, string> = {
  complete: '완료',
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
  llm_context_budget_exhausted: '모델 입력 예산 부족',
  review_revision_unavailable: '수정 분석 미실행(검토 지적 미해결)',
  synthesis_unavailable: '원인 분석 미실행으로 검토 생략',
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
  draft_changed_after_review: '검토 후 변경된 최종 초안은 미검토',
};

export function RcaEvaluation({ result }: { result: Row }) {
  const evaluation = obj(obj(result.quality).rca_evaluation);
  const label = (value: unknown) => evaluationLabels[str(value)] || str(value, '미확인');
  if (!Object.keys(evaluation).length)
    return <p>이전 결과: 분리된 분석 품질 검토 기록이 없습니다.</p>;
  if (evaluation.schema_version !== '1')
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
