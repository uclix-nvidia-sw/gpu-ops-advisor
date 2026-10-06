import type { ReactNode } from 'react';
import { reportRequestTime } from '../lib/reportPeriod';
import { ReportExecution, ReportOrigin, ReportPeriod, ReportScope } from './ReportMeta';
import { Link, useLocation } from 'react-router-dom';
import { errorText, obj, rows, str, strings, useResource, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { Badge, Empty, Modal } from './ui';
import { ObservationSnapshot, RawJson } from './ObservationSnapshot';
import { reportTitle, reportTopics } from '../lib/workflow';
import { topicDisplayBases } from '../lib/reportKinds';
import { groupLabel, metricValue, metricUnit, namespaceRows, reportReason } from '../lib/report';
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
  queue_reason: '대기 사유',
  deadline_at: '작업 기한',
  cancel_requested_at: '취소 요청 시각',
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
  topic_group_by: '소주제별 표시 기준',
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
  job_id: ['작업 ID', 'JC가 관리하는 RCA 또는 보고서 실행 작업의 고유 ID입니다.'],
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

export function AlarmIdentity({ record, compact = false }: { record: Row; compact?: boolean }) {
  const target = obj(record.target);
  const name =
    str(target.reason) ||
    str(target.title) ||
    str(record.title) ||
    str(record.symptom) ||
    str(target.alertname) ||
    '알람 이름 미확인';
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
      {(target.test_alarm === true || /synthetic/i.test(name) || !!target.test_id) && (
        <Badge status={null} label="테스트 알람" />
      )}
      {!compact && str(target.alertname) && target.alertname !== name && (
        <span className="cell-sub">{str(target.alertname)}</span>
      )}
      {!compact && <span className="cell-sub">{targets.join(' · ') || '발생 대상 미확인'}</span>}
      {!compact && str(record.symptom) && record.symptom !== name && (
        <span className="cell-sub">{str(record.symptom)}</span>
      )}
    </span>
  );
}
const valueLabels: Record<string, string> = {
  timeout: '시간 초과 (timeout)',
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
  scheduler: '자동 보고서 설정',
  previous_complete_day: '직전 완료일',
  previous_complete_week: '직전 완료 주',
  previous_complete_month: '직전 완료 월',
};
export function DataView({
  value,
  field = '',
  explain = false,
  fieldNames = {},
  reportDisplay = false,
  depth = 0,
  evidenceLabels = {},
}: {
  value: unknown;
  field?: string;
  explain?: boolean;
  fieldNames?: Record<string, string>;
  reportDisplay?: boolean;
  depth?: number;
  evidenceLabels?: Record<string, string>;
}) {
  if (
    ['evidence_refs', 'supporting_refs', 'contradicting_refs'].includes(field) &&
    Array.isArray(value)
  )
    return value.length ? (
      <ul>
        {strings(value).map((id) => (
          <li key={id} title={id}>
            {evidenceLabels[id] || '저장 근거 · 조회·판단 기록에서 상세 확인'}
          </li>
        ))}
      </ul>
    ) : (
      <span className="muted">기록 없음</span>
    );
  if (field === 'runbook_revisions' && Array.isArray(value))
    return (
      <ul>
        {rows(value).map((book, index) => (
          <li key={index} title={str(book.id)}>
            {str(book.knowledge_key, 'Runbook 이름 미확인')} (rev{' '}
            {String(book.revision ?? '미확인')}) · {str(book.title, '제목 미확인')}
          </li>
        ))}
      </ul>
    );
  if (field === 'model' && typeof value === 'object')
    return (
      <div>
        {str(obj(value).name) || str(obj(value).model_name) || '모델 이름 미확인'} · revision{' '}
        {String(obj(value).revision ?? '미확인')}
        <RawJson value={value} />
      </div>
    );
  if (field === 'knowledge' && Array.isArray(value))
    return (
      <ul>
        {rows(value).map((entry, index) => (
          <li key={index}>
            {str(entry.title) || str(entry.knowledge_key) || '지식 이름 미확인'} · revision{' '}
            {String(entry.revision ?? '미확인')}
            <RawJson value={entry} />
          </li>
        ))}
      </ul>
    );
  if (field === 'snapshot')
    return (
      <ObservationSnapshot value={value} fallback={<DataView value={value} depth={depth} />} />
    );
  if (field === 'sub_agent_id' && typeof value === 'string') {
    const match = /^observation-(\d+)-(\d+)$/.exec(value);
    if (match)
      return (
        <span title={value}>
          {Number(match[1]) + 1}차 수집 · 작업 {Number(match[2]) + 1}
        </span>
      );
  }
  if (field === 'loki_timestamp_ns' && typeof value === 'string' && /^\d{16,20}$/.test(value))
    return (
      <span title={value}>
        {new Date(Number(BigInt(value) / 1000000n)).toLocaleString('ko-KR', {
          timeZone: 'Asia/Seoul',
        })}{' '}
        KST
      </span>
    );
  if (field === 'source_position' && typeof obj(value).line === 'number')
    return <span>{Number(obj(value).line) + 1}번째 줄</span>;
  if (field === 'suggested_actions' && typeof value === 'string') {
    try {
      const actions = obj(JSON.parse(value));
      return (
        <div>
          원천 제안 조치:{' '}
          {strings(actions.repair_actions)
            .map((action) =>
              action === 'REBOOT_SYSTEM'
                ? '시스템 재부팅(REBOOT_SYSTEM)'
                : '등록되지 않은 원천 조치',
            )
            .join(' · ')}
          <p>실행 조건 미검증 · 미수행 · 담당자 확인 필요</p>
          <RawJson value={actions} />
        </div>
      );
    } catch {
      return <span>원천 제안 형식 미확인</span>;
    }
  }
  if (reportDisplay && field === 'topic_group_by')
    return (
      <dl className="live-details data-stacked">
        {Object.keys(obj(value)).map((id) => (
          <div key={id}>
            <dt>{id}</dt>
            <dd>{topicDisplayBases[id] || groupLabel(obj(value)[id])}</dd>
          </div>
        ))}
      </dl>
    );
  if (reportDisplay && field === 'timezone') return <span>한국 시간</span>;
  if (
    reportDisplay &&
    typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)
  )
    return <span>{formatDate(value)}</span>;
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
            <DataView
              value={v}
              explain={explain}
              fieldNames={fieldNames}
              depth={depth + 1}
              evidenceLabels={evidenceLabels}
              reportDisplay={reportDisplay}
            />
          </div>
        ))}
      </div>
    ) : (
      <span className="muted">기록 없음</span>
    );
  return (
    <dl className={`live-details ${depth >= 2 ? 'data-stacked' : ''}`} data-depth={depth}>
      {Object.entries(obj(value))
        .filter(([k]) => !(reportDisplay && k === 'group_by' && obj(value).topic_group_by))
        .filter(
          ([k]) =>
            ![
              'request_id',
              'checksum',
              '__tenant_id__',
              'content_hash',
              'knowledge_id',
              'model_id',
            ].includes(k),
        )
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
                    {fieldNames[k] || incidentFields[k]?.[0] || fieldLabels[k] || k}{' '}
                    <span aria-hidden="true">ⓘ</span>
                  </summary>
                  <code>{k}</code>
                  <p>
                    {incidentFields[k]?.[1] ||
                      '서버에 저장된 원본 값입니다. 값이 없으면 미확인으로 표시합니다.'}
                  </p>
                </details>
              ) : (
                fieldNames[k] || incidentFields[k]?.[0] || fieldLabels[k] || k
              )}
            </dt>
            <dd>
              <DataView
                value={v}
                field={k}
                explain={explain}
                fieldNames={fieldNames}
                depth={depth + 1}
                evidenceLabels={evidenceLabels}
                reportDisplay={reportDisplay}
              />
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
        <RawJson value={q.data} />
      </QueryState>
    </Modal>
  );
}
export function JobRows({ items }: { items: Row[] }) {
  const location = useLocation();
  const reportsOnly = location.pathname === '/reports';
  const from = location.pathname + location.search;
  if (reportsOnly) return <ReportHistory items={items} from={from} />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>분석 · 대상</th>
            <th>종류</th>
            <th>접수 시각</th>
            <th className="job-state-cell">실행 상태</th>
            <th className="job-state-cell">결과 품질</th>
            <th>최종 보고서</th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={str(j.id)} id={`report-row-${str(j.id)}`}>
              <td>
                <div className={j.kind === 'report' ? 'job-report-heading' : undefined}>
                  <Link
                    className="text-link"
                    state={{ from }}
                    to={
                      j.kind === 'report' || j.result_ref != null
                        ? `/${j.kind === 'rca' ? 'analyses' : 'reports'}/${str(j.id)}#final-report`
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
                  {j.kind === 'report' && <ReportOrigin value={j.report_origin} />}
                </div>
                {j.kind === 'rca' && <small className="cell-sub">작업 ID · {str(j.id)}</small>}
                {j.kind === 'report' ? (
                  <>
                    <details>
                      <summary>분석 주제 · 작업 ID</summary>
                      <p>{reportTopics(j)}</p>
                      <small>{str(j.id)}</small>
                    </details>
                    <ReportScope job={j} />
                    <div className="cell-sub">
                      분석 대상 기간: <ReportPeriod value={j.time_range} />
                    </div>
                    <div className="cell-sub">
                      요청 집계: {groupLabel(j.group_by, j.topic_group_by)}
                    </div>
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
                      ? '운영 분석 보고서'
                      : str(j.kind)}
                </td>
              )}
              <td className="job-received-time">
                {(j.kind === 'report'
                  ? reportRequestTime(str(j.created_at))
                  : formatDate(str(j.created_at))
                ).replace(/ (?=\d{2}:)/, '\n')}
              </td>
              <td className="job-state-cell">
                <Badge status={str(j.status)} />
              </td>
              <td className="job-state-cell">
                <Badge status={str(j.result_status) || null} />
              </td>
              {!reportsOnly && (
                <td>
                  {j.result_ref != null ? (
                    <Link
                      className="text-link"
                      state={{ from }}
                      to={`/${j.kind === 'rca' ? 'analyses' : 'reports'}/${str(j.id)}#final-report`}
                    >
                      최종 보고서 보기
                    </Link>
                  ) : (
                    '결과 미발행'
                  )}
                  <div>
                    <Link className="text-link" state={{ from }} to={`/jobs/${str(j.id)}`}>
                      작업 상태·시도 이력
                    </Link>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportHistory({ items, from }: { items: Row[]; from: string }) {
  // The API orders this filtered page by request time, newest first.
  const featured = items[0];
  const others = items.slice(1);
  const card = (job: Row, large = false) => (
    <article
      className={`report-history-card ${large ? 'report-history-featured' : 'report-history-compact'}`}
      key={str(job.id)}
      id={`report-row-${str(job.id)}`}
    >
      <header>
        <span className="report-history-id" title={str(job.id)}>
          ID {str(job.id).slice(0, 8)}
        </span>
        <div className="report-history-status">
          <span>
            실행 상태 <Badge status={str(job.status) || null} />
          </span>
          <span>
            결과 품질 <Badge status={str(job.result_status) || null} />
          </span>
        </div>
      </header>
      {large && <p className="report-featured-label">가장 최근 요청 · 요청 접수 시각 기준</p>}
      <h3 className="report-title-with-origin">
        <ReportOrigin value={job.report_origin} />
        <Link
          className="text-link report-history-title"
          state={{ from, reportList: from, reportRow: str(job.id) }}
          to={`/reports/${str(job.id)}#final-report`}
        >
          {reportTitle(job)}
        </Link>
      </h3>
      <dl className="report-history-meta">
        <div>
          <dt>요청 접수 시각</dt>
          <dd>{reportRequestTime(str(job.created_at))}</dd>
        </div>
        <div>
          <dt>분석 대상 기간</dt>
          <dd>
            <ReportPeriod value={job.time_range} />
          </dd>
        </div>
        <div>
          <dt>분석 대상</dt>
          <dd>
            <ReportScope job={job} />
          </dd>
        </div>
        <div>
          <dt>집계 기준</dt>
          <dd>{groupLabel(job.group_by, job.topic_group_by)}</dd>
        </div>
      </dl>
      {large &&
        (str(job.result_ref) ? (
          <ReportPreview job={job} />
        ) : (
          <div className="report-preview">
            <strong>{labels[str(job.status)] || '실행 상태 미확인'}</strong>
            <p>
              {job.started_at
                ? `실행 시작: ${reportRequestTime(str(job.started_at))}`
                : '아직 실행 시작 기록이 없습니다.'}
            </p>
            {job.queue_reason != null && (
              <p>{labels[str(job.queue_reason)] || str(job.queue_reason)}</p>
            )}
            <Link className="button" to={`/jobs/${str(job.id)}`} state={{ from }}>
              실행 상태 보기
            </Link>
          </div>
        ))}
      {str(job.result_ref) && (
        <Link className="text-link" to={`/jobs/${str(job.id)}`} state={{ from }}>
          작업 상태·시도 이력
        </Link>
      )}
      <details className="report-history-details">
        <summary>세부 주제 · 전체 작업 ID</summary>
        <p>{reportTopics(job)}</p>
        <code>{str(job.id)}</code>
      </details>
      {large && str(job.result_ref) && (
        <Link
          className="button primary"
          state={{ from, reportList: from, reportRow: str(job.id) }}
          to={`/reports/${str(job.id)}#final-report`}
        >
          보고서 읽기
        </Link>
      )}
    </article>
  );
  return (
    <div className="report-history-cards">
      {featured && card(featured, true)}
      {!featured && <p className="muted">아직 요청한 보고서가 없습니다.</p>}
      {others.map((job) => card(job))}
    </div>
  );
}

function ReportPreview({ job }: { job: Row }) {
  const query = useResource(`/reports/${encodeURIComponent(str(job.id))}`);
  if (query.isPending) return <p role="status">저장된 요약을 불러오는 중…</p>;
  if (query.isError)
    return (
      <div className="report-preview" role="alert">
        <p>요약을 불러오지 못했습니다. 보고서 본문은 아래 버튼으로 열 수 있습니다.</p>
        <button className="text-link" onClick={() => query.refetch()}>
          요약 다시 불러오기
        </button>
      </div>
    );
  const detail = obj(query.data);
  if (detail.id !== job.id || detail.result_ref !== job.result_ref)
    return <p className="muted">목록과 요약의 결과 참조가 다릅니다. 목록을 새로고침해 주세요.</p>;
  const result = obj(detail.result),
    topics = rows(result.topics);
  const metrics = topics.flatMap((topic) => rows(topic.metrics));
  const namespaces = namespaceRows(metrics);
  const reasons = [
    ...new Set(
      [
        ...topics.flatMap((topic) => strings(topic.missing_inputs)),
        ...metrics.flatMap((metric) => [
          ...strings(obj(metric.quality).excluded_reasons),
          ...(metric.value == null ? [str(obj(metric.quality).reason)] : []),
        ]),
      ].filter(Boolean),
    ),
  ];
  return (
    <section className="report-preview" aria-label="저장된 결과 요약">
      <div>
        <span>보고서 실행시간</span>
        <ReportExecution job={detail} />
      </div>
      <h4>핵심 결과</h4>
      {topics.length ? (
        <p>
          산출 완료 {topics.filter((t) => t.status === 'ready').length}개 · 부분 산출{' '}
          {topics.filter((t) => t.status === 'partial').length}개 · 판단 보류{' '}
          {topics.filter((t) => t.status === 'blocked').length}개 주제
        </p>
      ) : (
        <p>{str(result.summary, '요약에 사용할 주제별 기록이 없습니다. 본문을 확인하세요.')}</p>
      )}
      {namespaces.slice(0, 2).map(({ target, metrics: values }) => {
        const activity = values.namespace_connected_gpu_util;
        return (
          <p key={JSON.stringify(target)}>
            <strong>
              {str(target.cluster_id)} / {str(target.namespace)}
            </strong>
            <br />
            연결 GPU 평균 활동률:{' '}
            {activity
              ? `${metricValue(activity)}${activity.value == null ? '' : ` ${metricUnit(activity)}`}`
              : '미계산'}
          </p>
        );
      })}
      {namespaces.length > 2 && (
        <p>외 {namespaces.length - 2}개 Namespace는 본문에서 확인하세요.</p>
      )}
      {!!namespaces.length && (
        <p className="muted">연결 GPU의 관측 활동이며 Namespace의 실제 소비량은 아닙니다.</p>
      )}
      {!!reasons.length && (
        <div className="report-preview-limitations">
          <h4>자료 부족·주의사항</h4>
          <ul>
            {reasons.slice(0, 2).map((reason) => (
              <li key={reason}>{reportReason(reason)}</li>
            ))}
          </ul>
          {reasons.length > 2 && <p>추가 제한 {reasons.length - 2}개는 본문에서 확인하세요.</p>}
        </div>
      )}
    </section>
  );
}
