import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { canonical, obj, rows, str, useList, useResource, type Row } from '../lib/live';
import { Badge, Field, Notice } from './ui';
import { DataView, More, QueryState } from './live';
import { relationMismatch, returnPath } from '../lib/debug';

export function RawRecord({
  value,
  label = '저장 원본 · 시각 정밀도 유지',
}: {
  value: unknown;
  label?: string;
}) {
  return (
    <details>
      <summary>{label}</summary>
      <pre className="trace-json">{JSON.stringify(value ?? null, null, 2)}</pre>
    </details>
  );
}

// Arrays retain their order; missing and explicit null are different observations.
export function differences(
  left: Row,
  right: Row,
  prefix = '',
): { path: string; left: unknown; right: unknown }[] {
  return [...new Set([...Object.keys(left), ...Object.keys(right)])].sort().flatMap((key) => {
    const a = left[key],
      b = right[key],
      path = prefix ? `${prefix}.${key}` : key;
    if (a !== undefined && b !== undefined && canonical(a) === canonical(b)) return [];
    if (
      a &&
      b &&
      typeof a === 'object' &&
      typeof b === 'object' &&
      !Array.isArray(a) &&
      !Array.isArray(b)
    )
      return differences(obj(a), obj(b), path);
    return [{ path, left: a, right: b }];
  });
}
export function DifferenceTable({ left, right }: { left: Row; right: Row }) {
  const changes = differences(left, right);
  return changes.length ? (
    <div className="table-wrap">
      <table className="trace-diff">
        <thead>
          <tr>
            <th>필드</th>
            <th>기준</th>
            <th>비교 대상</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((d) => (
            <tr key={d.path}>
              <th>{d.path}</th>
              <td>
                <pre>{d.left === undefined ? '필드 없음' : JSON.stringify(d.left, null, 2)}</pre>
              </td>
              <td>
                <pre>{d.right === undefined ? '필드 없음' : JSON.stringify(d.right, null, 2)}</pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p>제공된 두 기록의 값이 같습니다. 조회되지 않은 데이터까지 같다는 의미는 아닙니다.</p>
  );
}

export function InputTrace({ trace }: { trace: Row }) {
  const snapshot = obj(obj(trace.incident_snapshot).record);
  const outbox = obj(obj(trace.outbox).record);
  const source = obj(snapshot.snapshot);
  const [baseline, setBaseline] = useState('incident');
  const inputs: Record<string, Row> = {
    incident: obj(source.input),
    outbox: obj(obj(outbox.input_snapshot).input),
    manual: obj(obj(obj(obj(trace.manual_request).record).envelope).input),
  };
  const names: Record<string, string> = {
    incident: '사건 고정 스냅샷의 input',
    outbox: '전달 요청의 input',
    manual: '즉시 보고서 요청의 input',
  };
  const sections = [
    [
      'incident_snapshot',
      '실행 당시 사건 증거',
      'jobs.(incident_id, evidence_version) → incident_evidence_versions.(incident_id, revision)',
    ],
    [
      'outbox',
      'JC 전달 기록',
      'jobs.(source_module, source_key) → enqueue_outbox.(source_module, source_key) · job_id 대조',
    ],
    [
      'manual_request',
      '즉시 보고서 원본',
      'jobs.source_key → manual_report_intents.source_key (backend 요청)',
    ],
    [
      'schedule',
      '정기 실행 회차·고정 일정',
      'jobs.id → schedule_occurrences.job_id → schedule_revisions.(schedule_id, revision)',
    ],
  ];
  return (
    <section className="stack" aria-label="작업 연결 추적">
      <h3>입력 전달 경로</h3>
      <p>
        현재 사건이나 최신 설정 대신 이 작업의 고정 키로 조회합니다. 각 원본에서 시각의 소수점까지
        확인할 수 있습니다.
      </p>
      {sections.map(([key, title, join]) => {
        const section = obj(trace[key]);
        return (
          <details key={key}>
            <summary>
              {title} ·{' '}
              {section.state === 'available'
                ? '기록 있음'
                : section.state === 'schema_unavailable'
                  ? '저장 구조 미설치'
                  : '연결 기록 없음'}
            </summary>
            <p>
              <code>{join}</code>
            </p>
            {section.state === 'available' ? (
              <>
                <DataView value={section.record} />
                <RawRecord value={section.record} />
                {key === 'schedule' && str(obj(obj(section.record).occurrence).schedule_id) && (
                  <Link to={`/schedules/${str(obj(obj(section.record).occurrence).schedule_id)}`}>
                    자동 보고서 설정 보기
                  </Link>
                )}
              </>
            ) : (
              <Notice>
                이 경로의 기록이 제공되지 않았습니다. 즉시 요청에는 일정이 없는 등 요청 종류에 따라
                정상적으로 비어 있을 수 있습니다.
              </Notice>
            )}
          </details>
        );
      })}
      <details>
        <summary>고정된 작업 입력·버전</summary>
        <RawRecord value={{ input_snapshot: trace.input_snapshot, versions: trace.versions }} />
      </details>
      <details>
        <summary>전달 전후 입력 비교</summary>
        <Field label="기준 단계">
          <select value={baseline} onChange={(e) => setBaseline(e.target.value)}>
            {Object.entries(names).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <p>
          기준: {names[baseline]} → 비교 대상: jobs.input_snapshot. 공통 필드만의 비교가 아니므로
          새로 추가된 필드도 표시합니다.
        </p>
        {Object.keys(inputs[baseline]).length ? (
          <DifferenceTable left={inputs[baseline]} right={obj(trace.input_snapshot)} />
        ) : (
          <Notice>기준 단계의 input이 없어 비교할 수 없습니다.</Notice>
        )}
      </details>
      <details>
        <summary>알람 수신·사건 연결 · {rows(obj(trace.alerts).items).length}건</summary>
        <p>
          <code>alert_events.receipt_id → incident_webhook_receipts.id</code> · 해당 사건의 수신
          이력이며 각 알람이 이 작업을 생성했다는 뜻은 아닙니다.
        </p>
        {obj(trace.alerts).state === 'schema_unavailable' ? (
          <Notice>알람 수신 테이블이 설치되지 않았습니다.</Notice>
        ) : !rows(obj(trace.alerts).items).length ? (
          <p>연결된 알람 수신 기록이 없습니다.</p>
        ) : (
          rows(obj(trace.alerts).items).map((a) => (
            <details key={str(a.id)}>
              <summary>
                {str(a.observed_at)} · {str(a.status)} · {str(a.disposition)}
              </summary>
              <DataView value={a} />
              <RawRecord value={a} />
            </details>
          ))
        )}
        {obj(trace.alerts).truncated === true && (
          <Notice>최근 200건만 표시합니다. 이전 기록은 이 응답에 포함되지 않았습니다.</Notice>
        )}
      </details>
    </section>
  );
}

export function StoredEvidence({
  job,
  attempt,
  onEvidence,
}: {
  job: Row;
  attempt: number;
  onEvidence: (id: string) => void;
}) {
  const q = useList(
    `/jobs/${encodeURIComponent(str(job.id))}/evidence?attempt=${attempt}&limit=50`,
  );
  const [filter, setFilter] = useState('');
  const [pair, setPair] = useState<string[]>([]);
  const visible = q.items.filter((r) =>
    `${str(r.query_id)} ${str(r.tool_status)} ${str(obj(r.quality).reason)}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  return (
    <section className="stack" aria-label="시도별 저장 근거">
      <h3>시도 {attempt}의 조회·판단 기록</h3>
      <Notice>
        저장 시각 순서입니다. 종료 시 일괄 저장되므로 실제 실행 순서·소요시간을 뜻하지 않습니다.
        sufficiency의 round·remaining과 계획 기록을 함께 대조하세요. 기록 없음은 미실행의 증거가
        아닙니다.
      </Notice>
      <Field label="불러온 기록에서 조회 ID·상태·사유 검색">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="D05, sufficiency, synthesis, partial…"
        />
      </Field>
      <p>
        {q.items.length}건 불러옴 · 검색 결과 {visible.length}건. 공개 결과가 참조하지 않은 저장
        근거도 포함합니다.
      </p>
      <QueryState query={q} empty={!q.items.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>조회·판단</th>
                <th>저장 시각 (UTC 원본)</th>
                <th>수집 상태·표본</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={str(r.id)}>
                  <td>
                    <button className="text-link" onClick={() => onEvidence(str(r.id))}>
                      {str(r.query_id, '조회 종류 미확인')}
                    </button>
                    <small className="cell-sub">{str(r.id)}</small>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={pair.includes(str(r.id))}
                        disabled={pair.length === 2 && !pair.includes(str(r.id))}
                        onChange={(e) =>
                          setPair(
                            e.target.checked
                              ? [...pair, str(r.id)]
                              : pair.filter((id) => id !== r.id),
                          )
                        }
                      />
                      요청 비교 선택
                    </label>
                  </td>
                  <td>{str(r.created_at)}</td>
                  <td>
                    <Badge status={str(r.tool_status)} /> ·{' '}
                    {String(obj(r.quality).sample_count ?? '미확인')}
                  </td>
                  <td>{str(obj(r.quality).reason, '기록 없음')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!!q.items.length && !visible.length && <p>현재 불러온 기록 중 검색 결과가 없습니다.</p>}
      </QueryState>
      <More query={q} />
      <p>
        두 기록을 선택하면 조회 인자·시간 범위·응답 해시를 비교합니다. 쿼리가 같아도 수집 목적이
        같다는 뜻은 아닙니다.
      </p>
      {pair.length === 2 && <EvidenceComparison job={str(job.id)} attempt={attempt} ids={pair} />}
    </section>
  );
}

function EvidenceComparison({
  job,
  attempt,
  ids,
}: {
  job: string;
  attempt: number;
  ids: string[];
}) {
  const path = (id: string) =>
    `/jobs/${encodeURIComponent(job)}/evidence/${encodeURIComponent(id)}?attempt=${attempt}`;
  const a = useResource(path(ids[0])),
    b = useResource(path(ids[1]));
  const valid = (record: Row | undefined, id: string) =>
    record && !relationMismatch(record, { id, job_id: job, attempt_no: attempt }).length;
  const select = (r: Row) => ({
    input: r.input,
    time_start: r.time_start,
    time_end: r.time_end,
    checksum: r.checksum,
    quality: r.quality,
  });
  return (
    <QueryState query={a}>
      <QueryState query={b}>
        {valid(a.data, ids[0]) && valid(b.data, ids[1]) ? (
          <section>
            <h4>
              {str(a.data?.query_id)} ↔ {str(b.data?.query_id)} 요청·응답 비교
            </h4>
            <DifferenceTable left={select(a.data!)} right={select(b.data!)} />
            <RawRecord
              value={{ 기준: select(a.data!), 비교대상: select(b.data!) }}
              label="비교에 사용한 요청·품질 원본"
            />
          </section>
        ) : (
          <Notice>연결 불일치: 작업·시도·근거 ID가 일치하지 않아 비교하지 않습니다.</Notice>
        )}
      </QueryState>
    </QueryState>
  );
}

export function JobComparison({ job, trace, from }: { job: Row; trace: Row; from?: unknown }) {
  const [params, setParams] = useSearchParams();
  const id = params.get('compare') || '';
  const [draft, setDraft] = useState(id);
  const other = useResource(id ? `/jobs/${encodeURIComponent(id)}` : null);
  const otherTrace = useResource(id ? `/jobs/${encodeURIComponent(id)}/trace` : null);
  return (
    <details open={!!id}>
      <summary>이전·다른 작업과 비교</summary>
      <form
        className="live-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          const next = new URLSearchParams(params);
          if (from) next.set('from', returnPath(from));
          if (draft.trim()) next.set('compare', draft.trim());
          else next.delete('compare');
          setParams(next);
        }}
      >
        <Field label="비교할 작업 ID">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} />
        </Field>
        <button className="button">비교</button>
      </form>
      {id && (
        <>
          <p>
            기준: {str(job.id)} / 비교 대상: {id}. 같은 작업의 시도 비교와는 다릅니다.
          </p>
          <QueryState query={other}>
            <QueryState query={otherTrace}>
              <DifferenceTable
                left={{
                  input: trace.input_snapshot,
                  versions: trace.versions,
                  status: job.status,
                  termination_reason: job.termination_reason,
                  result: job.result_ref != null ? job.result : null,
                }}
                right={{
                  input: otherTrace.data?.input_snapshot,
                  versions: otherTrace.data?.versions,
                  status: other.data?.status,
                  termination_reason: other.data?.termination_reason,
                  result: other.data?.result_ref != null ? other.data.result : null,
                }}
              />
              <Link to={`/jobs/${encodeURIComponent(id)}?tab=evidence`}>
                비교 대상의 조회·판단 기록 열기
              </Link>
            </QueryState>
          </QueryState>
        </>
      )}
    </details>
  );
}
