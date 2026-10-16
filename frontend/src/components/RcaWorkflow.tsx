import { RcaObjective } from './RcaEvaluation';
import { useState } from 'react';
import { obj, rows, str, strings, useList, useResource, type Row } from '../lib/live';
import { relationMismatch } from '../lib/debug';
import { queryName } from '../lib/report';
import { formatDate } from '../lib/domain';
import { rcaReasons } from '../lib/rcaLabels';
import { Field, Modal, Notice } from './ui';
import { DataView, More, QueryState } from './live';
import { RawRecord } from './TraceView';
import { EvidenceEvaluation } from './RcaDebug';
import { evaluationLabels } from './RcaEvaluation';
import { rcaStages, RcaStageDetails, stageForRecord, reviewStatus } from './RcaEvaluationTrace';
import './RcaWorkflow.css';

const steps: Record<string, { title: string; actor: string; purpose: string }> = {
  incident_snapshot: {
    title: '조사 대상 사건 원본 보존',
    actor: '코드',
    purpose: '실행 당시 사건·대상·기간을 고정된 원본에서 읽습니다.',
  },
  alert_clues: {
    title: '알람 단서 추출',
    actor: '코드',
    purpose: '알람의 오류 코드·대상 단서를 추출합니다. 원인이나 장치 신원 확정은 아닙니다.',
  },
  runbook_selection: {
    title: '조사 지침 선택',
    actor: '코드',
    purpose: '등록된 Runbook을 검색하고 적용·호환 조건을 확인합니다.',
  },
  runbook: {
    title: '선택 Runbook 원문 보존',
    actor: '코드',
    purpose: '선택한 조사 지침을 나중에 대조할 수 있도록 본문·버전·출처를 저장합니다.',
  },
  investigation_plan: {
    title: '조회할 자료와 목적 정리',
    actor: '코드',
    purpose: 'Runbook의 필수·허용 조회와 각 조회의 목적을 정합니다.',
  },
  investigation_plan_extension: {
    title: '조사 계획 보완',
    actor: '코드',
    purpose: '관측과 기존 정책에 따라 허용된 조사 범위를 보완합니다.',
  },
  observation_plan: {
    title: '이번 회차 수집 계획',
    actor: '코드',
    purpose: '이번 회차 조회의 순서·의존성과 실행 예산을 배정합니다.',
  },
  evidence_evaluation: {
    title: '수집 평가·다음 조회 선택',
    actor: '코드 / 허용 시 선택 LLM',
    purpose: '수집 요건·부족 조건과 조회 허용 규칙으로 보완 수집 또는 종료를 결정합니다.',
  },
  unexpected_evidence: {
    title: '예상과 다른 관측에 대한 판단 · 구 기록',
    actor: '코드',
    purpose:
      '예전 버전이 관측의 예외 조건과 Runbook의 대응 정책을 기록한 항목입니다. 프로그램 오류라는 뜻은 아닙니다. 기록된 조건과 조사 확장 여부를 확인하세요.',
  },
  ...rcaStages,
};
function recordType(id: string) {
  if (/^D\d+$/.test(id)) return '자료 수집';
  if (['incident_snapshot', 'runbook', 'rca_analysis_draft'].includes(id))
    return '원문·중간 결과 보존';
  if (['evidence_interpretation', 'rca_synthesis', 'analysis_review'].includes(id))
    return 'LLM 처리';
  return steps[id] ? '코드 판단' : '종류 미지원';
}
const label = (v: unknown) =>
  evaluationLabels[str(v)] ||
  rcaReasons[str(v)] ||
  (
    {
      ok: '응답·기록 확보',
      empty: '빈 응답',
      partial: '일부만 수집',
      unavailable: '수집 불가',
    } as Record<string, string>
  )[str(v)] ||
  str(v, '기록 없음');
const recorded = (v: unknown) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('ko-KR') : str(v, '미기록');
const stepFor = (id: string) =>
  steps[id] ||
  (/^D\d+$/.test(id)
    ? {
        title: `${id} · ${queryName(id)}`,
        actor: '수집 코드 · MCP',
        purpose: '계획에 포함된 관측 조회를 실행하고 응답과 수집 제한을 보존합니다.',
      }
    : {
        title: id || '종류 미확인',
        actor: '담당 미기록',
        purpose: '이 기록의 처리 방식에 대한 화면 설명이 없습니다. 저장 원문을 확인하세요.',
      });

export function RcaWorkflowButton({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="button primary" onClick={() => setOpen(true)} disabled={!jobId}>
        워크플로우 디버깅
      </button>
      {open && <WorkflowDialog jobId={jobId} onClose={() => setOpen(false)} />}
    </>
  );
}

function WorkflowDialog({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const q = useResource(`/jobs/${encodeURIComponent(jobId)}`);
  return (
    <Modal title="RCA 워크플로우 디버깅" wide onClose={onClose}>
      <QueryState query={q}>
        {q.data &&
          (q.data.id === jobId && q.data.kind === 'rca' ? (
            <WorkflowAttempts job={q.data} />
          ) : (
            <Notice tone="warning">작업 연결 불일치: 요청한 RCA 작업의 기록이 아닙니다.</Notice>
          ))}
      </QueryState>
    </Modal>
  );
}

function WorkflowAttempts({ job }: { job: Row }) {
  const [attempt, setAttempt] = useState(job.attempt_no);
  const attempts = [...new Set([job.attempt_no, ...rows(job.attempts).map((a) => a.attempt_no)])]
    .filter((n): n is number => typeof n === 'number' && Number.isInteger(n) && n >= 0)
    .sort((a, b) => b - a);
  return (
    <div className="stack">
      <p>
        기록을 선택하면 <strong>무엇을 했나 → 왜 했나 → 어떻게 했나 → 결과·한계 → 연결 근거</strong>
        를 확인할 수 있습니다.
      </p>
      <Field label="조사 시도">
        <select
          value={typeof attempt === 'number' ? attempt : ''}
          onChange={(e) => setAttempt(Number(e.target.value))}
        >
          {!attempts.length && <option value="">시도 기록 없음</option>}
          {attempts.map((n) => (
            <option key={n} value={n}>
              시도 {n}
              {n === job.attempt_no ? ' · 최신' : ' · 과거'}
            </option>
          ))}
        </select>
      </Field>
      <Notice>
        아래는 저장 기록 순서입니다. 조회 번호·생성 시각만으로 실제 실행 시작 순서를 확정하지
        않습니다. 병렬 조회와 미기록 시간은 구분해야 합니다. 실행 중에는 아직 저장되지 않은 단계가
        있을 수 있습니다. 원문·중간 결과 보존 기록은 새로운 조회나 LLM 실행 단계가 아닙니다. LLM
        담당 표시와 실제 모델 호출 여부도 구분해서 확인하세요.
      </Notice>
      {typeof attempt === 'number' && (
        <WorkflowRecords key={attempt} jobId={str(job.id)} attempt={attempt} />
      )}
    </div>
  );
}

function WorkflowRecords({ jobId, attempt }: { jobId: string; attempt: number }) {
  const q = useList(`/jobs/${encodeURIComponent(jobId)}/evidence?attempt=${attempt}&limit=50`);
  const [selected, setSelected] = useState('');
  const id = selected || str(q.items[0]?.id);
  const detail = useResource(
    id
      ? `/jobs/${encodeURIComponent(jobId)}/evidence/${encodeURIComponent(id)}?attempt=${attempt}`
      : null,
  );
  const index = q.items.findIndex((r) => r.id === id);
  const planId = str(q.items.find((r) => r.query_id === 'investigation_plan')?.id);
  const plan = useResource(
    planId
      ? `/jobs/${encodeURIComponent(jobId)}/evidence/${encodeURIComponent(planId)}?attempt=${attempt}`
      : null,
  );
  const validPlan =
    plan.data &&
    !relationMismatch(plan.data, { id: planId, job_id: jobId, attempt_no: attempt }).length
      ? plan.data
      : undefined;
  const mismatch = detail.data
    ? relationMismatch(detail.data, { id, job_id: jobId, attempt_no: attempt })
    : [];
  if (q.items.some((r) => relationMismatch(r, { job_id: jobId, attempt_no: attempt }).length))
    return (
      <Notice tone="warning">목록 연결 불일치: 다른 작업·시도의 기록은 표시하지 않습니다.</Notice>
    );
  return (
    <>
      <p>
        {q.items.length}개 기록 불러옴{q.hasNextPage ? ' · 추가 기록 있음' : ''}
      </p>
      <QueryState query={q} empty={!q.items.length}>
        <div className="rca-workflow-layout">
          <nav aria-label="워크플로우 기록 선택" className="stack">
            {q.items.map((record, i) => (
              <button
                key={str(record.id)}
                className={`button ${record.id === id ? 'primary' : ''}`}
                aria-current={record.id === id ? 'step' : undefined}
                onClick={() => setSelected(str(record.id))}
              >
                기록 {i + 1} ·{' '}
                {(stageForRecord(record, q.items) || stepFor(str(record.query_id))).title}
                <small>
                  {typeof record.round === 'number'
                    ? `${record.round + 1}회차 · `
                    : typeof obj(record.quality).round === 'number'
                      ? `${Number(obj(record.quality).round) + 1}회차 · `
                      : ''}
                  {reviewStatus(record) ??
                    label(obj(record.quality).execution_status || record.tool_status)}
                </small>
              </button>
            ))}
            <More query={q} />
          </nav>
          <div className="stack">
            <div className="head-actions">
              <button
                className="button"
                disabled={index <= 0}
                onClick={() => setSelected(str(q.items[index - 1]?.id))}
              >
                이전 기록
              </button>
              <button
                className="button"
                disabled={index < 0 || index + 1 >= q.items.length}
                onClick={() => setSelected(str(q.items[index + 1]?.id))}
              >
                다음 기록
              </button>
            </div>
            <QueryState query={detail}>
              {mismatch.length ? (
                <Notice tone="warning">
                  연결 불일치: {mismatch.join(', ')}. 다른 작업·시도의 근거는 표시하지 않습니다.
                </Notice>
              ) : (
                detail.data && (
                  <RcaWorkflowRecord
                    record={detail.data}
                    investigationPlan={validPlan}
                    relatedRecords={q.items}
                    onEvidence={setSelected}
                  />
                )
              )}
            </QueryState>
            <details>
              <summary>계획·결정 기록으로 이동</summary>
              {q.items
                .filter((r) =>
                  [
                    'investigation_plan',
                    'observation_plan',
                    'evidence_evaluation',
                    'investigation_decision',
                  ].includes(str(r.query_id)),
                )
                .map((r) => (
                  <button
                    key={str(r.id)}
                    className="text-link"
                    onClick={() => setSelected(str(r.id))}
                  >
                    {(stageForRecord(r) || stepFor(str(r.query_id))).title} · {str(r.id)}
                  </button>
                ))}
              <p>
                현재 불러온 기록의 링크입니다. 계획과 선택 이유가 미기록이면 실행 이유를 추정하지
                않습니다.
              </p>
            </details>
          </div>
        </div>
      </QueryState>
    </>
  );
}

export function RcaWorkflowRecord({
  record,
  investigationPlan,
  relatedRecords = [],
  onEvidence,
}: {
  record: Row;
  investigationPlan?: Row;
  relatedRecords?: Row[];
  onEvidence: (id: string) => void;
}) {
  const kind = str(record.query_id),
    step = stageForRecord(record, relatedRecords) || stepFor(kind),
    body = obj(record.snapshot),
    meta = obj(record.quality),
    diagnostics = obj(body.diagnostics);
  const reason =
    body.failure_reason ||
    diagnostics.error_code ||
    body.reason ||
    body.stop_reason ||
    meta.failure_reason ||
    meta.reason;
  const plan: Row[] = rows(body.runbooks).flatMap((book) =>
    rows(book.steps).map((s) => ({ ...s, revision_id: book.revision_id })),
  );
  const queryPlans = /^D\d+$/.test(kind)
    ? rows(obj(investigationPlan?.snapshot).runbooks).flatMap((book) =>
        rows(book.steps).filter((s) => s.query_id === kind),
      )
    : [];
  const refs = [
    ...new Set([
      ...strings(body.input_evidence_refs),
      ...strings(body.evidence_refs),
      ...strings(body.observation_refs),
      ...strings(diagnostics.input_evidence_refs),
      ...(typeof body.parent_plan_id === 'string' ? [body.parent_plan_id] : []),
      ...(typeof body.validation_evidence_id === 'string' ? [body.validation_evidence_id] : []),
      ...(typeof (body.selection_evidence_id ?? meta.selection_evidence_id) === 'string'
        ? [str(body.selection_evidence_id ?? meta.selection_evidence_id)]
        : []),
    ]),
  ];
  const sameDraft =
    body.analysis_id == null
      ? []
      : relatedRecords.filter(
          (r) => r.id !== record.id && obj(r.quality).analysis_id === body.analysis_id,
        );
  const selectedBooks =
    kind === 'runbook_selection'
      ? relatedRecords.filter(
          (r) => r.query_id === 'runbook' && obj(r.quality).selection_evidence_id === record.id,
        )
      : [];
  return (
    <article className="stack" aria-label="워크플로우 단계 판단 근거">
      <h3>{step.title}</h3>
      <section>
        <h4>무엇을 했나</h4>
        <p>
          기록 성격:{' '}
          {kind === 'analysis_review' && reviewStatus(record) === '미실행'
            ? '미실행 상태 기록'
            : recordType(kind)}
        </p>
        <p>
          담당: {step.actor} · 저장된 단계 상태:{' '}
          {reviewStatus(record) ??
            label(
              body.execution_status || meta.execution_status || body.status || record.tool_status,
            )}
        </p>
        <details>
          <summary>기록 식별값</summary>
          기록 ID: <code>{str(record.id)}</code> · 조회/단계 ID: <code>{kind}</code>
        </details>
      </section>
      <section>
        <h4>왜 했나 · 저장된 이유와 결정</h4>
        <p>{step.purpose}</p>
        {queryPlans.map((s, i) => (
          <p key={i}>
            저장된 조사 계획:{' '}
            {s.required === true
              ? '필수 조회'
              : s.required === false
                ? '선택 조회'
                : '필수 여부 미기록'}{' '}
            · {str(s.purpose, '목적 기록 없음')}.{' '}
            <button className="text-link" onClick={() => onEvidence(str(investigationPlan?.id))}>
              계획 근거 열기
            </button>
          </p>
        ))}
        {reason ? (
          <p>
            {reason === 'review_claims_withheld'
              ? '검토 지적에 따라 주장 제외·권고 보류'
              : label(reason)}
          </p>
        ) : !queryPlans.length ? (
          <details>
            <summary>수행 사유 기록</summary>개별 수행 사유는 기록 없음
          </details>
        ) : (
          <p>
            계획의 목적이며 실제 호출 시작 순서를 증명하지 않습니다. 선택 조회의 실행 조건은 해당
            회차의 수집 평가에서 확인하세요.
          </p>
        )}
        {body.action != null && (
          <p>
            다음 행동:{' '}
            {(
              {
                collect: '보완 수집',
                revise: '분석 수정',
                withhold: '문제된 주장 보류',
                reuse: '기존 RCA 판단 유지',
                finish: '조사 종료',
              } as Record<string, string>
            )[str(body.action)] || str(body.action)}
          </p>
        )}
        {strings(body.selected_queries).length > 0 && (
          <p>선택 조회: {strings(body.selected_queries).join(', ')}</p>
        )}
        {plan.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>조회·필수 여부</th>
                  <th>저장된 목적</th>
                  <th>선택 조건</th>
                </tr>
              </thead>
              <tbody>
                {plan.map((s, i) => (
                  <tr key={i}>
                    <td>
                      {str(s.query_id)} ·{' '}
                      {s.required === true ? '필수' : s.required === false ? '선택' : '미기록'}
                    </td>
                    <td>{str(s.purpose, '목적 기록 없음')}</td>
                    <td>
                      <DataView
                        value={
                          s.selection ?? {
                            priority: s.priority,
                            exploratory_llm: s.exploratory_llm,
                          }
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {kind === 'evidence_evaluation' && <EvidenceEvaluation record={body} />}
      </section>
      <section>
        <h4>어떻게 했나 · 처리 기준과 실행 기록</h4>
        {kind === 'runbook' && (
          <p>
            선택한 지침의 버전 ID: <code>{str(obj(record.input).revision_id, '미기록')}</code>
            {' · '}지침 버전: {str(record.query_version, '미기록')}
            {' · '}출처:{' '}
            {(
              { published: '발행된 지침', builtin: '제품에 내장된 일반 조사 지침' } as Record<
                string,
                string
              >
            )[str(meta.origin)] || str(meta.origin, '미기록')}
          </p>
        )}
        <details>
          <summary>실행 시간·모델·횟수 상세</summary>
          <DataView
            value={{
              started_at: body.started_at ?? meta.started_at,
              completed_at: body.completed_at ?? meta.completed_at,
              elapsed_seconds: body.elapsed_seconds ?? meta.elapsed_seconds,
              model: body.model ?? meta.model,
              attempts: body.attempts ?? meta.attempts,
              input_view_hash: body.input_view_hash,
              reason,
            }}
          />
        </details>
        <RcaStageDetails record={record} onEvidence={onEvidence} compact />
        {meta.selection_reason != null && (
          <p>조회 연결 선택 사유: {label(meta.selection_reason)}</p>
        )}
      </section>
      <section>
        <h4>결과·남은 한계</h4>
        <RcaObjective value={body.decision_assessment} />
        {kind === 'rca_synthesis' && body.generation_mode === 'combined' && (
          <section aria-label="통합 작성 결과">
            <h4>증거 해석·RCA 분석 · 작성 LLM</h4>
            <p>
              {diagnostics.adoption === 'interpretation_only'
                ? '해석은 보존했지만 원인 분석은 채택하지 못했습니다.'
                : diagnostics.adoption === 'validated_response'
                  ? '해석·분석 응답이 코드 검증을 통과했습니다. 원인 확정이나 품질 검토 통과를 뜻하지 않습니다.'
                  : '작성 결과를 채택하지 못했습니다. 실패 사유와 요청 이력을 확인하세요.'}
            </p>
            <details>
              <summary>확인 내용·미확인·상충·한계</summary>
              <DataView value={body.interpretation} />
            </details>
          </section>
        )}
        <StoredOutcome record={record} />
        {/^D\d+$/.test(kind) ? (
          <>
            <p>
              조회 범위: 클러스터 {str(record.cluster_id, '미기록')} · 노드{' '}
              {str(obj(obj(record.input).target).node, '별도 필드 미기록')}
            </p>
            <p>
              조회 기간: {formatDate(str(record.time_start ?? obj(record.time_range).start))} ~{' '}
              {formatDate(str(record.time_end ?? obj(record.time_range).end))}
            </p>
            <p>
              요청 결과: {label(record.tool_status)} · 수집 완료 표시:{' '}
              {meta.complete === true ? '완료' : meta.complete === false ? '불완전' : '미기록'}
            </p>
            <p>
              요청 성공은 필요한 증거 확보나 원인 확인을 뜻하지 않습니다. 아래 응답·품질 원문과 후속
              해석을 함께 확인하세요.
            </p>
            <details>
              <summary>수집 품질 원문</summary>
              <DataView value={record.quality} />
            </details>
          </>
        ) : !steps[kind] ? (
          <p>이 종류의 결과 설명은 지원하지 않습니다. 저장 원문을 확인하세요.</p>
        ) : null}
        {strings(body.limitations).map((limit, i) => (
          <p key={i}>{limit}</p>
        ))}
        <h4>입력·결과와 판단 근거</h4>
        {selectedBooks.length > 0 && (
          <p>
            선택 결과 · 사용한 지침 원문:{' '}
            {selectedBooks.map((r) => (
              <button className="text-link" key={str(r.id)} onClick={() => onEvidence(str(r.id))}>
                {str(r.id)}
              </button>
            ))}
          </p>
        )}
        {refs.length ? (
          <p>
            연결 근거:{' '}
            {refs.map((ref) => (
              <button className="text-link" key={ref} onClick={() => onEvidence(ref)}>
                {ref}
              </button>
            ))}
          </p>
        ) : (
          <p>별도 입력 근거 ID 기록 없음</p>
        )}
        {sameDraft.length > 0 && (
          <p>
            같은 분석본의 관련 기록:{' '}
            {sameDraft.map((r) => (
              <button className="text-link" key={str(r.id)} onClick={() => onEvidence(str(r.id))}>
                {(stageForRecord(r) || stepFor(str(r.query_id))).title} · {str(r.id)}
              </button>
            ))}
          </p>
        )}
        <p>
          다음 저장 기록은 상단 버튼으로 이동합니다. 목록에는 개별 입력 참조가 없어, 뒤에 저장됐다는
          이유만으로 이 근거를 사용했다고 판단하지 않습니다.
        </p>
        <details>
          <summary>저장된 요청 인자·대상·기간</summary>
          <DataView
            value={{
              input: record.input,
              scope: record.scope,
              time_start: record.time_start,
              time_end: record.time_end,
            }}
          />
        </details>
        {!rcaStages[kind] && kind !== 'evidence_evaluation' && kind !== 'investigation_plan' && (
          <details>
            <summary>저장된 결과 원문</summary>
            <DataView value={record.snapshot} />
          </details>
        )}
        {kind === 'rca_synthesis' && (
          <details>
            <summary>분석 결과·진단 원문</summary>
            <DataView
              value={{ hypotheses: body.hypotheses, limitations: body.limitations, diagnostics }}
            />
          </details>
        )}
        <RawRecord value={record} label="전체 저장 원문 · 품질·입력·결과 대조" />
      </section>
    </article>
  );
}

function StoredOutcome({ record }: { record: Row }) {
  const body = obj(record.snapshot);
  switch (record.query_id) {
    case 'unexpected_evidence':
      return (
        <>
          <p>
            기록된 예외 조건:{' '}
            {Array.isArray(body.events)
              ? strings(body.events).map(label).join(' · ') ||
                '문장으로 표시할 조건 없음 · 원문 확인 필요'
              : '미기록'}
          </p>
          <p>
            일반 조사 확장 사유: {label(body.general_extension_reason)} · 확장 억제 여부:{' '}
            {body.general_extension_suppressed === true
              ? '억제함'
              : body.general_extension_suppressed === false
                ? '억제하지 않음'
                : '미기록'}
            . 실제 추가 조회는 이후 수집 기록에서 확인하세요.
          </p>
        </>
      );
    case 'runbook':
      return (
        <>
          <p>저장한 조사 지침: {str(body.title, '제목 미기록')}</p>
          <p>
            지침에 적힌 원인 설명: {str(body.claim, '미기록')} (이번 사건에서 확인된 결론과는
            다릅니다.)
          </p>
          <p>
            이 지침을 다시 실행한 것이 아닙니다. 뒤의 분석·검토 기록에서 이 근거 ID를 실제로
            사용했는지 확인하세요.
          </p>
        </>
      );
    case 'runbook_selection':
      return (
        <ul>
          {rows(record.snapshot).map((row, i) => (
            <li key={i}>
              지침 {str(row.revision_id, '식별자 미기록')}:{' '}
              {(
                {
                  retrieved:
                    '사건 단서와 맞는 조사 후보로 찾았습니다. 적용 조건 충족 여부는 별도로 판단합니다.',
                  invalid_contract: '지침 형식이 맞지 않아 선택에서 제외했습니다.',
                  general_available:
                    '일반 조사 지침을 추가 조사 후보로 준비했습니다. 실제 적용 여부는 조사 계획에서 확인하세요.',
                } as Record<string, string>
              )[str(row.status)] || '이 선택 결과의 설명은 지원하지 않습니다. 원문을 확인하세요.'}
              {row.reason != null && <> · 기록된 이유: {label(row.reason)}</>}
            </li>
          ))}
        </ul>
      );
    case 'alert_clues':
      return (
        <>
          <p>
            알람이 보고한 대상: {str(body.k8s_node_name, '미기록')} · 구성 요소:{' '}
            {str(body.component, '미기록')}
          </p>
          <p>
            알람에서 찾은 오류 코드:{' '}
            {Array.isArray(body.error_codes)
              ? strings(body.error_codes).join(', ') || '없음'
              : '미기록'}
          </p>
          <p>알람 설명: {str(body.reason, '미기록')}</p>
          <p>
            서로 다른 값이 있어 사용하지 않은 단서:{' '}
            {Array.isArray(body.conflicts)
              ? strings(body.conflicts).join(', ') || '없음'
              : '미기록'}
            . 이 단서는 확인된 원인이 아닙니다.
          </p>
        </>
      );
    case 'observation_plan':
      return (
        <>
          <p>
            한 번에 실행하도록 설정한 조회 수:{' '}
            {typeof body.concurrency === 'number' ? body.concurrency : '미기록'}. 아래 나열 순서가
            실제 시작 순서는 아닙니다.
          </p>
          <ul>
            {rows(body.assignments).map((row, i) => (
              <li key={i}>
                {queryName(str(row.query_id))} ({str(row.query_id)}) — 조회 예산{' '}
                {recorded(obj(row.budget).queries)}회, 자료 연결 탐색 예산{' '}
                {recorded(obj(row.budget).discovery)}회
              </li>
            ))}
          </ul>
        </>
      );
    case 'investigation_plan':
      return (
        <>
          <p>
            반드시 확인할 조회:{' '}
            {strings(body.required_queries)
              .map((q) => `${queryName(q)} (${q})`)
              .join(' · ') || '기록 없음'}
          </p>
          <p>
            수행 가능한 조회:{' '}
            {strings(body.allowed_queries)
              .map((q) => `${queryName(q)} (${q})`)
              .join(' · ') || '기록 없음'}
            . 허용됐다고 모두 실행하는 것은 아닙니다.
          </p>
        </>
      );
    case 'investigation_plan_extension':
      return (
        <>
          <p>
            추가한 조사 지침: {str(body.runbook_revision_id, '미기록')} · revision{' '}
            {recorded(body.revision)}
          </p>
          <ul>
            {rows(body.steps).map((row, i) => (
              <li key={i}>
                {queryName(str(row.query_id))} ({str(row.query_id)}):{' '}
                {str(row.purpose, '목적 미기록')}
              </li>
            ))}
          </ul>
        </>
      );
    default:
      return null;
  }
}
