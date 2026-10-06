import { obj, rows, str, strings, topics, type Row } from './live';

export type WorkflowStep = {
  title: string;
  owner: string;
  purpose: string;
  inspect: string;
  expected: string;
  missing: string;
  fields: string[];
};
export const commonSteps: WorkflowStep[] = [
  {
    title: '작업 접수와 실행',
    owner: 'Job Controller → Worker',
    purpose: '접수된 작업을 Worker가 가져가고 시도별로 실행합니다.',
    inspect: 'id · kind · status · queue_reason · stage · attempts',
    expected:
      'job ID는 접수 근거입니다. started_at·attempts는 실행 이력이며 queued는 실패가 아닙니다.',
    missing:
      'Worker claim·lease·heartbeat 원문은 이 API에 없습니다. service-status와 서버 로그를 확인하세요.',
    fields: [
      'id',
      'kind',
      'status',
      'queue_reason',
      'stage',
      'attempt_no',
      'started_at',
      'deadline_at',
      'attempts',
    ],
  },
  {
    title: '관측 근거 수집',
    owner: 'Worker → Grafana MCP → 저장 근거',
    purpose: '대상과 기간에 맞는 관측을 가져오고 품질·누락을 기록합니다.',
    inspect: 'evidence_refs → GET /evidence/{id} → query_id · quality · snapshot',
    expected:
      '동일 job/attempt, 조회 구간, datasource, tool_status를 대조합니다. 빈 결과와 수집 실패를 구분하세요.',
    missing:
      '근거는 종료 후 저장됩니다. 실행 중 개별 조회의 실시간 진행률·요청 쿼리 원문은 확인할 수 없습니다.',
    fields: ['evidence_refs'],
  },
];
export const rcaSteps: WorkflowStep[] = [
  {
    title: '알람과 사건 연결',
    owner: 'Grafana → Incident',
    purpose: '수신 사건과 조사 작업의 입력을 연결합니다.',
    inspect: 'incident_id → 사건 target · evidence_version · rca_eligibility_reason',
    expected: '사건 ID와 대상이 일치하는지 확인합니다. 알람 해제·사건 종결·검토 상태는 별개입니다.',
    missing:
      'Webhook 수신 원문과 outbox 전달 이력은 GUI API에 없습니다. 사건이 없다는 이유만으로 알람 미수신을 확정하지 마세요.',
    fields: ['incident_id', 'target', 'scope', 'symptom', 'purpose_ids'],
  },
  ...commonSteps,
  {
    title: 'Runbook·근거 판단',
    owner: 'RCA Agent',
    purpose: 'Runbook 또는 근거 기반 조사 경로에서 사실·후보·목적별 판단을 만듭니다.',
    inspect: 'quality.analysis · assessments · facts · cause_candidates · missing_inputs',
    expected:
      'fast_path·sufficiency·status와 후보의 지지/반박 근거를 함께 확인합니다. 성공 상태만으로 원인을 확정하지 않습니다.',
    missing:
      '아직 공개되지 않은 판단·내부 후보는 조회되지 않습니다. 근거 목록의 조사 단계 기록도 확인하세요.',
    fields: ['quality', 'assessments', 'facts', 'cause_candidates', 'missing_inputs'],
  },
  {
    title: '설명과 권고',
    owner: 'RCA Agent · LLM',
    purpose: '검증된 근거로 설명과 검토 권고를 작성합니다.',
    inspect: 'narrative_status · llm_usage · recommendations · limitations',
    expected:
      'LLM 응답 사용 기록은 원격 호출 전체 감사 기록이 아닙니다. 0건만으로 미호출·연결 실패를 확정하지 않습니다.',
    missing: '모델 요청·응답 원문은 이 화면의 검증 범위 밖입니다. 장비 조치는 사람이 수행합니다.',
    fields: ['narrative_status', 'llm_usage', 'recommendations', 'limitations'],
  },
];
export const reportSteps: WorkflowStep[] = [
  {
    title: '즉시 요청·정기 발생',
    owner: 'GUI → Backend / Backend Scheduler',
    purpose: '분석 범위·완료된 기간·주제를 고정해 보고서를 접수합니다.',
    inspect: 'scope · time_range · timezone · topic_ids · group_by · comparison_range',
    expected:
      '즉시 요청은 202와 job_id를 확인합니다. 정기는 occurrence의 accepted·job_id를 작업과 대조합니다.',
    missing:
      '일정의 pending은 전달 대기이며 작업 실행이 아닙니다. 내부 outbox·접수 receipt 원문은 제공되지 않습니다.',
    fields: [
      'scope',
      'time_range',
      'timezone',
      'topic_ids',
      'group_by',
      'topic_group_by',
      'comparison_range',
      'parent_job_id',
    ],
  },
  commonSteps[0],
  {
    title: 'DB 스냅샷·공개 RCA',
    owner: 'Ops Agent → PostgreSQL',
    purpose: '기준 시각의 사건·공개 RCA·조치 기록을 분석에 사용합니다.',
    inspect: 'data_cutoff_at · report_db_snapshot 근거의 snapshot',
    expected:
      '해당 보고서의 기준 시각과 저장 스냅샷을 대조합니다. 최신 사건과 과거 보고서의 차이는 곧 오류가 아닙니다.',
    missing:
      '근거 참조만으로 스냅샷 내용을 확인했다고 볼 수 없습니다. 근거 불러오기에서 실제 내용을 열어보세요.',
    fields: ['data_cutoff_at', 'evidence_refs'],
  },
  commonSteps[1],
  {
    title: '주제별 결정적 계산',
    owner: 'Ops Agent · O01–O11',
    purpose: '코드가 수치·단위·분모·대상·제한 사유를 계산합니다.',
    inspect: 'versions.criteria · topics[].metrics · denominator · method · quality',
    expected:
      'null과 0을 구분합니다. O08 criteria 1.2의 연결 GPU 활동률은 Namespace 실사용률이 아닙니다. 요청/적용 집계 축을 대조하세요.',
    missing:
      '다른 criteria의 값을 같은 기준으로 비교하지 마세요. 미지원 group_by는 blocked 사유를 확인합니다.',
    fields: ['versions', 'topics', 'measurements'],
  },
  {
    title: '설명·권고 검증',
    owner: 'Ops Agent · LLM',
    purpose: '계산한 사실을 설명하고 제공된 권고의 근거와 보류 사유를 확인합니다.',
    inspect: 'narrative · narrative_status · llm_usage · topics[].recommendations',
    expected:
      '설명 실패에도 유효 수치를 유지합니다. value_refs·evidence_refs를 대조하고 withheld·not_performed를 실제 수행으로 해석하지 않습니다.',
    missing:
      '병렬 Observation Sub-agent·보완 조회·Synthesis 확장은 현재 문서상 목표입니다. 저장 데이터 없이 실행 완료로 표시하지 않습니다.',
    fields: ['narrative', 'narrative_status', 'llm_usage', 'topics', 'limitations'],
  },
];
export const publicationStep: WorkflowStep = {
  title: '저장·공개·화면 소비',
  owner: 'Worker → Job Controller → Backend → GUI',
  purpose: '검증된 후보 중 JC가 공개한 결과를 조회합니다.',
  inspect: 'result_ref · result_status · result · versions',
  expected:
    'result_ref와 결과 본문을 함께 확인합니다. succeeded와 partial/blocked는 동시에 존재할 수 있습니다.',
  missing:
    '후보 업로드·해시 검증·공개 트랜잭션의 내부 로그는 API에 없습니다. 공개 결과만 검증할 수 있습니다.',
  fields: ['result_ref', 'result_status', 'termination_reason', 'versions'],
};

export function workflowValues(step: WorkflowStep, job: Row) {
  const result = job.result_ref != null ? obj(job.result) : {};
  return Object.fromEntries(step.fields.map((key) => [key, job[key] ?? result[key] ?? null]));
}
export function reportMetrics(result: Row) {
  const fromTopics = rows(result.topics).flatMap((topic) => rows(topic.metrics));
  return fromTopics.length ? fromTopics : rows(result.measurements);
}
export function reportTitle(job: Row) {
  const ids = strings(job.topic_ids);
  const purpose =
    ids.length === 11 && Object.keys(obj(job.topic_group_by)).length === 11
      ? 'GPU 운영 종합보고서'
      : ids.length === 1 && ids[0] === 'O08' && strings(job.group_by).includes('namespace')
        ? 'Namespace별 GPU 사용 분석'
        : ids.length > 1
          ? `GPU 운영 보고서 · ${ids.length}개 주제`
          : reportTopics(job);
  const start = Date.parse(str(obj(job.time_range).start));
  const end = Date.parse(str(obj(job.time_range).end));
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return purpose;
  const date = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  // A period ending at midnight covers the preceding day; keep exact times in the detail.
  const first = date.format(start);
  const last = date.format(end - 1);
  return `${first === last ? first : `${first} ~ ${last}`} · ${purpose}`;
}
export function reportTopics(job: Row) {
  return (
    strings(job.topic_ids)
      .map((id) => (/^O(0[1-9]|1[01])$/.test(id) ? topics[Number(id.slice(1)) - 1] : id))
      .join(' · ') || '분석 주제 미확인'
  );
}
export function reportScopeClusters(job: Row) {
  return rows(obj(job.scope).clusters).map((cluster) => ({
    cluster: str(cluster.cluster_id, '클러스터 미확인'),
    namespaces:
      cluster.namespaces === null
        ? '전체 Namespace'
        : cluster.namespaces === undefined
          ? 'Namespace 범위 미확인'
          : strings(cluster.namespaces).join(', ') || '선택된 Namespace 없음',
  }));
}
