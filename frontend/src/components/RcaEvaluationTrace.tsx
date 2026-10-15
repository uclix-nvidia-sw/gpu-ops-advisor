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
              </p>
              {typeof meta.attempts === 'number' && (
                <p>
                  논리 모델 요청 {meta.attempts}회{meta.model ? ` · ${str(meta.model)}` : ''}
                </p>
              )}
              {typeof obj(meta.usage).request_attempts === 'number' && (
                <p>
                  전송 시도 {String(obj(meta.usage).request_attempts)}회 · 사용 토큰{' '}
                  {String(obj(meta.usage).total_tokens ?? '미확인')}
                </p>
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
