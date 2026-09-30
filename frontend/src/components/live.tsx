import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { errorText, obj, str, useResource, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { Badge, Empty, Modal } from './ui';
export function QueryState({
  query,
  empty = false,
  children,
}: {
  query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  empty?: boolean;
  children: ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="live-state" role="status">
        서버에서 불러오는 중…
      </div>
    );
  if (query.isError)
    return (
      <div className="live-state" role="alert">
        <h3>데이터를 가져오지 못했습니다.</h3>
        <p>{errorText(query.error)}</p>
        <button className="button" onClick={() => query.refetch()}>
          다시 시도
        </button>
      </div>
    );
  if (empty)
    return (
      <Empty
        title="저장된 결과가 없습니다."
        description="선택한 범위에서 서버에 등록된 기록이 없습니다."
      />
    );
  return <>{children}</>;
}
export function More({
  query,
}: {
  query: { hasNextPage: boolean; isFetchingNextPage: boolean; fetchNextPage: () => unknown };
}) {
  return query.hasNextPage ? (
    <div className="form-actions">
      <button
        className="button"
        disabled={query.isFetchingNextPage}
        onClick={() => query.fetchNextPage()}
      >
        {query.isFetchingNextPage ? '불러오는 중…' : '더 보기'}
      </button>
    </div>
  ) : null;
}
export const CommandError = ({ error }: { error: string }) =>
  error ? (
    <p className="form-error" role="alert">
      {error}
    </p>
  ) : null;
const fieldLabels: Record<string, string> = {
  reason: '사유',
  status: '상태',
  tool_status: '조회 품질',
  quality: '관측 품질',
  source: '출처',
  items: '기록',
  snapshot: '관측 스냅샷',
  time_start: '시작 시각',
  time_end: '종료 시각',
  start: '시작',
  end: '종료',
  scope: '범위',
  clusters: 'CPC 목록',
  cluster_id: 'CPC',
  namespaces: 'Namespace',
  observed_at: '관측 시각',
  created_at: '생성 시각',
  checked_at: '확인 시각',
  valid_from: '유효 시작',
  valid_to: '유효 종료',
  evidence_refs: '근거 참조',
  target: '대상',
  kind: '종류',
  live_query_configured: '실시간 조회 연결',
  metrics: '관측 수치',
  title: '제목',
  summary: '요약',
  text: '내용',
  result_status: '결과 품질',
  narrative_status: '설명 상태',
  unit: '단위',
  value: '값',
  name: '이름',
  attempt_no: '시도 번호',
  started_at: '실행 시작',
  finished_at: '실행 종료',
  stage: '단계',
  termination_reason: '종료 사유',
  error_code: '오류 코드',
  visibility: '공개 범위',
  compatibility: '호환 조건',
  source_refs: '출처 참조',
  frequency: '반복 주기',
  local_time: '실행 시각',
  timezone: '시간대',
  period: '분석 기간',
  calendar: '실행 조건',
  report_request: '보고서 조건',
  report_spec: '보고서 조건',
  scheduled_for: '예정 시각',
  period_start: '보고 기간 시작',
  period_end: '보고 기간 종료',
  performed_by_verified: '조치자 확인 여부',
  pending: '전달 대기',
  topic_ids: '분석 주제',
  group_by: '집계 기준',
  performed_by: '수행자',
  action_summary: '조치 요약',
  occurred_at: '발생 시각',
  time_range: '조회 기간',
  purpose_ids: '조사 목적',
  symptom: '관측 증상',
  pod_uid: 'Pod UID',
  gpu_uuid: 'GPU UUID',
  node_uid: 'Node UID',
  namespace: 'Namespace',
  subject_type: '검토 대상 종류',
  subject_id: '검토 대상 ID',
  collection_status: '수집 상태',
};
const valueLabels: Record<string, string> = {
  live_observation_not_configured: '실시간 관측 소스가 연결되지 않았습니다.',
  stored_snapshot: '저장된 관측 스냅샷',
  only_verified_stored_snapshots_available:
    '검증된 저장 관측만 조회할 수 있습니다. 실시간 소스는 미연결 상태입니다.',
  common: '공통 지식',
  scoped: '범위 지정',
  ok: '정상',
  rca: 'RCA 조사',
  report: '보고서',
  chatbot: 'Assistant',
  incident: '사건·알림',
  scheduler: '정기 일정',
  previous_complete_day: '직전 완료일',
  previous_complete_week: '직전 완료 주',
  previous_complete_month: '직전 완료 월',
};
export function DataView({ value, field = '' }: { value: unknown; field?: string }) {
  if (field === 'namespaces' && value === null) return <span>전체 Namespace</span>;
  if (value === null || value === undefined) return <span className="muted">미확인</span>;
  if (typeof value === 'boolean') return <span>{value ? '사용' : '미사용'}</span>;
  if (typeof value !== 'object')
    return (
      <span className="data-text">
        {typeof value === 'string' &&
        /(_at|_from|_to)$/.test(field) &&
        Number.isFinite(Date.parse(value))
          ? formatDate(value)
          : valueLabels[String(value)] || labels[String(value)] || String(value)}
      </span>
    );
  if (Array.isArray(value))
    return value.length ? (
      <div className="stack">
        {value.map((v, i) => (
          <div className="data-item" key={i}>
            <DataView value={v} />
          </div>
        ))}
      </div>
    ) : (
      <span className="muted">기록 없음</span>
    );
  return (
    <dl className="live-details">
      {Object.entries(obj(value))
        .filter(([k]) => k !== 'request_id')
        .map(([k, v]) => (
          <div key={k}>
            <dt>{fieldLabels[k] || k}</dt>
            <dd>
              <DataView value={v} field={k} />
            </dd>
          </div>
        ))}
    </dl>
  );
}
export function EvidenceDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useResource(`/evidence/${encodeURIComponent(id)}`);
  return (
    <Modal title="관측 근거 상세" wide onClose={onClose}>
      <QueryState query={q}>
        <DataView value={q.data} />
      </QueryState>
    </Modal>
  );
}
export function JobRows({ items }: { items: Row[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>작업</th>
            <th>종류</th>
            <th>접수 시각</th>
            <th>실행 상태</th>
            <th>결과 품질</th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={str(j.id)}>
              <td>
                <Link className="text-link" to={`/jobs/${str(j.id)}`}>
                  {str(j.title, str(j.id))}
                </Link>
                <small className="cell-sub">{str(j.stage, '단계 미확인')}</small>
              </td>
              <td>
                {str(j.kind) === 'rca'
                  ? 'RCA 조사'
                  : str(j.kind) === 'report'
                    ? '보고서'
                    : str(j.kind)}
              </td>
              <td>{formatDate(str(j.created_at))}</td>
              <td>
                <Badge status={str(j.status)} />
              </td>
              <td>
                <Badge status={str(j.result_status) || null} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
