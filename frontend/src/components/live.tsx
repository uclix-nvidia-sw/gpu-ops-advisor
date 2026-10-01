import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { errorText, obj, str, useResource, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { Badge, Empty, Modal } from './ui';
import { reportScope, reportTitle, reportTopics } from '../lib/workflow';
import { groupLabel } from '../lib/report';
export function QueryState({
  query,
  empty = false,
  emptyTitle = '저장된 결과가 없습니다.',
  emptyDescription = '선택한 범위에서 서버에 등록된 기록이 없습니다.',
  children,
}: {
  query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  empty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
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
  if (empty) return <Empty title={emptyTitle} description={emptyDescription} />;
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
const incidentFields: Record<string, [string, string]> = {
  id: ['식별 ID', '이 기록을 구분하는 고유 ID입니다.'],
  job_id: ['작업 ID', 'JC가 관리하는 RCA 실행 작업의 고유 ID입니다.'],
  alertname: [
    '알람 이름',
    '알람 생산자가 지정한 규칙 이름입니다. 확정된 장애 원인을 뜻하지 않습니다.',
  ],
  node: ['노드', '알람에 기록된 노드 이름입니다.'],
  pod: ['Pod', '알람에 기록된 Pod 이름입니다.'],
  container: ['컨테이너', '알람에 기록된 컨테이너 이름입니다.'],
  alarm_status: [
    '알람 상태',
    '발생 중은 알람 조건이 활성화된 상태, 해제됨은 해제 알림을 수신한 상태입니다. 사건 종결과는 별개입니다.',
  ],
  alarm_resolved_at: [
    '알람 해제 시각',
    '알람 해제가 기록된 시각입니다. 장비 복구를 확정하는 시각은 아닙니다.',
  ],
  state: ['사건 처리 상태', '열림 → 확인됨 → 종결로 관리하는 사건 처리 상태입니다.'],
  review_status: [
    '검토 상태',
    '사람이 사건을 검토하는 진행 상태입니다. RCA 실행 상태와는 별개입니다.',
  ],
  analyses: ['연결된 RCA 작업', '이 사건에 연결된 조사 작업과 각 작업의 실행 상태입니다.'],
  analysis_profile_revision: ['분석 정책 버전', '이 사건의 분석에 지정된 정책 revision입니다.'],
  asset_key: [
    '자산 연결 키',
    '사건과 자산을 연결하는 저장 식별자입니다. 값이 없으면 연결 여부를 확인할 수 없습니다.',
  ],
  raw_asset: ['원본 자산 정보', '사건에 저장된 원본 자산 식별 정보입니다.'],
  correlation_key: ['상관관계 키', '관련 사건을 연결하기 위해 저장된 키입니다.'],
  correlation_status: ['상관관계 상태', '사건 간 연결에 관해 저장된 상태입니다.'],
  dedup_group: ['중복 판별 그룹', '반복 알람을 같은 사건으로 묶을 때 사용하는 그룹 키입니다.'],
  event_key: ['이벤트 식별 키', '중복 접수를 판별하는 사건 이벤트 키입니다.'],
  episode_key: ['에피소드 키', '연속된 사건 구간을 식별하기 위해 저장된 키입니다.'],
  evidence_version: [
    '사건 근거 버전',
    'RCA 입력으로 보존한 사건 스냅샷의 revision입니다. 수집 근거 개수가 아닙니다.',
  ],
  version: ['기록 버전', '변경 충돌을 방지하기 위한 기록 버전입니다.'],
  last_evidence_hash: ['최근 근거 해시', '사건 근거가 이전과 같은지 비교하는 값입니다.'],
  rca_eligibility_reason: [
    'RCA 접수 판단 사유',
    '새 RCA 작업의 접수 대상 여부를 판단한 사유 코드입니다.',
  ],
  fingerprint: ['알람 지문', '알람 생산자가 제공하는 알람 식별 값입니다.'],
  starts_at: ['알람 시작 시각', '원본 알람에 기록된 시작 시각입니다.'],
  first_seen: ['최초 관측 시각', '이 사건이 처음 관측된 시각입니다.'],
  last_seen: ['최근 관측 시각', '이 사건이 마지막으로 관측된 시각입니다.'],
  episode_started_at: ['사건 구간 시작', '현재 사건 에피소드의 시작 시각입니다.'],
  last_observed_at: ['최근 알람 관측', '이 사건에 연결된 알람의 최근 관측 시각입니다.'],
  observation_count: ['알람 관측 횟수', '같은 사건에 연결되어 기록된 알람 관측 횟수입니다.'],
  observation_gap_seconds: [
    '관측 간격 기준(초)',
    '사건 구간을 구분할 때 사용하는 알람 관측 간격 기준입니다.',
  ],
  ended_at: ['사건 구간 종료', '사건 에피소드가 종료된 시각입니다.'],
  ended_reason: ['구간 종료 사유', '사건 에피소드가 종료된 사유입니다.'],
  closed_at: ['사건 종결 시각', '사건 처리 상태를 종결로 변경한 시각입니다.'],
  prior_incident_id: ['이전 사건 ID', '앞선 사건 에피소드의 식별자입니다.'],
  memo: ['검토 메모', '사용자가 사건에 남긴 메모입니다.'],
  updated_at: ['최근 변경 시각', '이 기록을 마지막으로 변경한 시각입니다.'],
};

export function AlarmIdentity({ record }: { record: Row }) {
  const target = obj(record.target);
  const name =
    str(target.alertname) || str(record.title) || str(record.symptom) || '알람 이름 미확인';
  const targets = [
    ['cluster_id', 'CPC'],
    ['namespace', 'Namespace'],
    ['node', '노드'],
    ['pod', 'Pod'],
    ['container', '컨테이너'],
    ['gpu_uuid', 'GPU'],
    ['node_uid', 'Node UID'],
    ['pod_uid', 'Pod UID'],
  ].flatMap(([key, label]) => {
    const value = str(target[key]) || (key === 'cluster_id' ? str(record.cluster_id) : '');
    return value ? [`${label}: ${value}`] : [];
  });
  return (
    <span className="alarm-identity">
      <strong>{name}</strong>
      <span className="cell-sub">{targets.join(' · ') || '발생 대상 미확인'}</span>
      {str(record.symptom) && record.symptom !== name && (
        <span className="cell-sub">{str(record.symptom)}</span>
      )}
    </span>
  );
}
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
export function DataView({
  value,
  field = '',
  explain = false,
}: {
  value: unknown;
  field?: string;
  explain?: boolean;
}) {
  if (field === 'namespaces' && value === null) return <span>전체 Namespace</span>;
  if (value === null || value === undefined) return <span className="muted">미확인</span>;
  if (typeof value === 'boolean') return <span>{value ? '예 (true)' : '아니요 (false)'}</span>;
  if (field === 'alarm_status' && value === 'resolved') return <span>해제됨</span>;
  if (typeof value !== 'object')
    return (
      <span className="data-text">
        {typeof value === 'string' &&
        /(_at|_from|_to|_seen)$/.test(field) &&
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
            <DataView value={v} explain={explain} />
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
            <dt>
              {explain ? (
                <details className="field-help">
                  <summary
                    title={
                      incidentFields[k]?.[1] || `${fieldLabels[k] || k}: 서버에 저장된 필드입니다.`
                    }
                  >
                    {incidentFields[k]?.[0] || fieldLabels[k] || k}{' '}
                    <span aria-hidden="true">ⓘ</span>
                  </summary>
                  <code>{k}</code>
                  <p>
                    {incidentFields[k]?.[1] ||
                      '서버에 저장된 원본 값입니다. 값이 없으면 미확인으로 표시합니다.'}
                  </p>
                </details>
              ) : (
                incidentFields[k]?.[0] || fieldLabels[k] || k
              )}
            </dt>
            <dd>
              <DataView value={v} field={k} explain={explain} />
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
  const location = useLocation();
  const reportsOnly = location.pathname === '/reports';
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>분석 · 대상</th>
            {!reportsOnly && <th>종류</th>}
            <th>접수 시각</th>
            <th>실행 상태</th>
            <th>결과 품질</th>
            {!reportsOnly && <th>최종 보고서</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={str(j.id)} id={`report-row-${str(j.id)}`}>
              <td>
                <Link
                  className="text-link"
                  state={
                    reportsOnly
                      ? { reportList: location.pathname + location.search, reportRow: str(j.id) }
                      : undefined
                  }
                  to={
                    j.kind === 'report' && j.result_ref != null
                      ? `/reports/${str(j.id)}#final-report`
                      : `/jobs/${str(j.id)}`
                  }
                >
                  {j.kind === 'rca' ? (
                    <AlarmIdentity record={j} />
                  ) : j.kind === 'report' ? (
                    <strong>{reportTitle(j)}</strong>
                  ) : (
                    str(j.title, str(j.id))
                  )}
                </Link>
                {j.kind === 'rca' && <small className="cell-sub">작업 ID · {str(j.id)}</small>}
                {j.kind === 'report' ? (
                  <>
                    <details>
                      <summary>분석 주제 · 작업 ID</summary>
                      <p>{reportTopics(j)}</p>
                      <small>{str(j.id)}</small>
                    </details>
                    <div className="cell-sub">대상: {reportScope(j)}</div>
                    <div className="cell-sub">
                      분석 기간: {formatDate(str(obj(j.time_range).start))} –{' '}
                      {formatDate(str(obj(j.time_range).end))}
                    </div>
                    <div className="cell-sub">요청 집계: {groupLabel(j.group_by)}</div>
                  </>
                ) : (
                  <small className="cell-sub">{str(j.stage, '단계 미확인')}</small>
                )}
              </td>
              {!reportsOnly && (
                <td>
                  {str(j.kind) === 'rca'
                    ? 'RCA 조사'
                    : str(j.kind) === 'report'
                      ? '보고서'
                      : str(j.kind)}
                </td>
              )}
              <td>{formatDate(str(j.created_at))}</td>
              <td>
                <Badge status={str(j.status)} />
              </td>
              <td>
                <Badge status={str(j.result_status) || null} />
              </td>
              {!reportsOnly && (
                <td>
                  {j.result_ref != null ? (
                    <Link
                      className="text-link"
                      to={`/${j.kind === 'rca' ? 'analyses' : 'reports'}/${str(j.id)}#final-report`}
                    >
                      최종 보고서 보기
                    </Link>
                  ) : (
                    '미발행'
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
