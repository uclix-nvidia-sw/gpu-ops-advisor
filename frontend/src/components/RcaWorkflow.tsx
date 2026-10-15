import { useState } from 'react';
import { obj, rows, str, strings, useList, useResource, type Row } from '../lib/live';
import { relationMismatch } from '../lib/debug';
import { queryName } from '../lib/report';
import { rcaReasons } from '../lib/rcaLabels';
import { Field, Modal, Notice } from './ui';
import { DataView, More, QueryState } from './live';
import { RawRecord } from './TraceView';
import { EvidenceEvaluation } from './RcaDebug';
import { evaluationLabels } from './RcaEvaluation';
import { rcaStages, RcaStageDetails } from './RcaEvaluationTrace';
import './RcaWorkflow.css';

const steps: Record<string, { title: string; actor: string; purpose: string }> = {
  incident_snapshot: {
    title: '조사할 사건 고정',
    actor: '코드',
    purpose: '실행 당시 사건·대상·기간을 고정된 원본에서 읽습니다.',
  },
  alert_clues: {
    title: '알람 단서 추출',
    actor: '코드',
    purpose: '알람의 오류 코드·대상 단서를 추출합니다. 원인이나 장치 신원 확정은 아닙니다.',
  },
  runbook_selection: {
    title: 'Runbook 선택',
    actor: '코드',
    purpose: '등록된 Runbook을 검색하고 적용·호환 조건을 확인합니다.',
  },
  investigation_plan: {
    title: '조사 계획',
    actor: '코드',
    purpose: 'Runbook의 필수·허용 조회와 각 조회의 목적을 정합니다.',
  },
  investigation_plan_extension: {
    title: '조사 계획 보완',
    actor: '코드',
    purpose: '관측과 기존 정책에 따라 허용된 조사 범위를 보완합니다.',
  },
  observation_plan: {
    title: '수집 배정',
    actor: '코드',
    purpose: '이번 회차 조회의 순서·의존성과 실행 예산을 배정합니다.',
  },
  evidence_evaluation: {
    title: '수집 평가·다음 조회 선택',
    actor: '코드 / 허용 시 선택 LLM',
    purpose: '수집 요건·부족 조건과 조회 허용 규칙으로 보완 수집 또는 종료를 결정합니다.',
  },
  ...rcaStages,
};
const label = (v: unknown) => evaluationLabels[str(v)] || rcaReasons[str(v)] || str(v, '기록 없음');
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
        단계를 선택하면 <strong>무엇을 했나 → 왜 했나 → 어떻게 했나 → 입력·결과 근거</strong>를
        확인할 수 있습니다.
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
        있을 수 있습니다.
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
                기록 {i + 1} · {stepFor(str(record.query_id)).title}
                <small>
                  {typeof record.round === 'number'
                    ? `${record.round + 1}회차 · `
                    : typeof obj(record.quality).round === 'number'
                      ? `${Number(obj(record.quality).round) + 1}회차 · `
                      : ''}
                  {label(obj(record.quality).execution_status || record.tool_status)}
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
                    {stepFor(str(r.query_id)).title} · {str(r.id)}
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
  onEvidence,
}: {
  record: Row;
  investigationPlan?: Row;
  onEvidence: (id: string) => void;
}) {
  const kind = str(record.query_id),
    step = stepFor(kind),
    body = obj(record.snapshot),
    meta = obj(record.quality),
    diagnostics = obj(body.diagnostics);
  const reason = body.reason || body.stop_reason || meta.reason || diagnostics.error_code;
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
    ]),
  ];
  return (
    <article className="stack" aria-label="워크플로우 단계 판단 근거">
      <h3>{step.title}</h3>
      <section>
        <h4>무엇을 했나</h4>
        <p>
          담당: {step.actor} · 실행/수집 상태:{' '}
          {label(
            body.execution_status || meta.execution_status || body.status || record.tool_status,
          )}
        </p>
        <p>
          기록 ID: <code>{str(record.id)}</code> · 조회/단계 ID: <code>{kind}</code>
        </p>
      </section>
      <section>
        <h4>왜 했나 · 저장된 이유와 결정</h4>
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
            {label(reason)} <code>{str(reason)}</code>
          </p>
        ) : !queryPlans.length ? (
          <p>
            이 기록의 개별 수행 사유는 기록 없음. 조사 계획의 목적·필수 여부와 수집 평가의 선택
            조건을 함께 확인하세요.
          </p>
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
              { collect: '보완 수집', revise: '분석 수정', finish: '조사 종료' } as Record<
                string,
                string
              >
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
        <p>구현된 단계 역할: {step.purpose}</p>
        <p>이 역할 설명은 개별 실행 성공이나 모델이 실제로 읽은 자료 전체를 보증하지 않습니다.</p>
        <DataView
          value={{
            started_at: body.started_at ?? meta.started_at,
            completed_at: body.completed_at ?? meta.completed_at,
            elapsed_seconds: body.elapsed_seconds ?? meta.elapsed_seconds,
            model: body.model ?? meta.model,
            attempts: body.attempts ?? meta.attempts,
            input_view_hash: body.input_view_hash,
          }}
        />
        <RcaStageDetails record={record} onEvidence={onEvidence} />
        {meta.selection_reason != null && (
          <p>조회 연결 선택 사유: {label(meta.selection_reason)}</p>
        )}
      </section>
      <section>
        <h4>입력·결과와 판단 근거</h4>
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
          <DataView value={record.snapshot} />
        )}
        {kind === 'rca_synthesis' && (
          <DataView
            value={{ hypotheses: body.hypotheses, limitations: body.limitations, diagnostics }}
          />
        )}
        <RawRecord value={record} label="전체 저장 원문 · 품질·입력·결과 대조" />
      </section>
    </article>
  );
}
