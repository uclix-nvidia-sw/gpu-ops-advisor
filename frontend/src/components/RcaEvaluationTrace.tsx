import { obj, rows, str, strings, type Row } from '../lib/live';
import { evaluationLabels } from './RcaEvaluation';

export const rcaStages: Record<string, { title: string; actor: string; purpose: string }> = {
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
    purpose: '수정·보완 수집·종료를 결정합니다.',
  },
};
const label = (v: unknown) => evaluationLabels[str(v)] || str(v, '기록 없음');
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
          const step = rcaStages[str(record.query_id)];
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
                    { revise: '분석 수정', collect: '추가 수집', finish: '종료' } as Record<
                      string,
                      string
                    >
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
  const step = rcaStages[str(record.query_id)];
  if (!step) return null;
  const body = obj(record.snapshot);
  const interpretation = obj(body.interpretation);
  const review = obj(body.review);
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
      {body.execution_status != null && <p>실행 상태: {label(body.execution_status)}</p>}
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
            {str(claim.id)} · {str(claim.source)}
          </strong>
          : {str(claim.statement)} {refs(claim.supporting_refs)}
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
