import { obj, rows, str, strings, type Row } from '../lib/live';
import { evaluationLabels } from './RcaEvaluation';
import { modelExecution, rcaReasons } from '../lib/rcaLabels';

export const rcaStages: Record<string, { title: string; actor: string; purpose: string }> = {
  rca_result_frozen: {
    title: '보고서용 RCA 근거 자료 고정',
    actor: '코드',
    purpose:
      '확인 사실·채택 및 보류·평가·종료 이유를 구조화해 고정합니다. RCA 자체를 보고서 문장으로 다시 쓰지 않습니다.',
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
export function stageForRecord(record: Row) {
  const kind = str(record.query_id);
  const combined =
    (obj(record.snapshot).generation_mode ?? obj(record.quality).generation_mode) === 'combined';
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
    <section aria-label="RCA 평가 실행 흐름">
      <h3>평가 실행 흐름</h3>
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
              {['evidence_interpretation', 'analysis_review'].includes(str(record.query_id)) && (
                <RequestChecks value={meta.request_checks} />
              )}
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
}: {
  record: Row;
  onEvidence?: (id: string) => void;
}) {
  const step = stageForRecord(record);
  if (!step) return null;
  const body = obj(record.snapshot);
  const interpretation = obj(body.interpretation);
  const review = obj(body.review);
  const synthesis = obj(body.diagnostics);
  const allocation = obj(synthesis.budget_allocation);
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
      <h3>
        {step.title} · {step.actor}
      </h3>
      <p>{step.purpose}</p>
      {record.query_id === 'rca_result_frozen' && (
        <p>
          RCA 근거 자료 식별값: <code>{str(body.material_hash, '미기록')}</code>. 이후 보고서
          작성에서 이 자료가 바뀌면 결과 공개를 중단합니다.
        </p>
      )}
      {record.query_id === 'report_assembly' && (
        <p>
          작성 방식:{' '}
          {obj(body.report).method === 'llm_prioritized'
            ? '확정된 문장을 LLM이 정렬'
            : obj(body.report).method === 'deterministic_fallback'
              ? '코드의 기본 순서로 작성'
              : '미기록'}
          . 원인과 RCA 판정은 다시 생성하지 않았습니다.
          {obj(body.report).fallback_reason != null && (
            <> 기본 순서 사용 이유: {label(obj(body.report).fallback_reason)}.</>
          )}
        </p>
      )}
      {['evidence_interpretation', 'rca_synthesis', 'analysis_review'].includes(
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
          {synthesis.error_code != null && (
            <p>
              분석 실패 사유: {label(synthesis.error_code)} <code>{str(synthesis.error_code)}</code>
            </p>
          )}
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
      {body.execution_status != null && <p>저장된 단계 상태: {label(body.execution_status)}</p>}
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
      {['evidence_interpretation', 'analysis_review'].includes(str(record.query_id)) && (
        <RequestChecks value={body.request_checks} />
      )}
      <StageUsage value={body.usage} />
      {body.analysis_id != null && (
        <p>
          검토 대상 초안: <code>{str(body.analysis_id)}</code>
        </p>
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
