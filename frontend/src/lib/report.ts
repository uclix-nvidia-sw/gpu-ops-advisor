import { rcaLabels } from './rcaLabels';
import { obj, rows, str, strings, topics, type Row } from './live';

const names: Record<string, string> = {
  namespace_connected_gpu_count: '기간 중 연결이 확인된 GPU',
  namespace_activity_valid_hours: '활동률 계산에 사용한 시간',
  namespace_connected_gpu_util: '연결 GPU 평균 활동률',
  low_gpu_hours: '저활동 관측 시간',
  difference: 'GPU 활동률 편차',
  incident_rate: '관측 GPU시간당 사건 발생률',
  mapped_incident_relations: '사건 당시 GPU·작업 연결',
  gpu_shortage: 'GPU 부족량',
  observed_change: '조치 전후 관측 변화',
  energy_before: '조치 전 관측 에너지',
  energy_after: '조치 후 관측 에너지',
  observed_energy_reduction: '관측 에너지 감소량',

  observed_gpu_count: '관측된 GPU',
  observed_devices: '관측된 GPU',
  mapped_gpu_count: 'Pod 연결이 확인된 GPU',
  mapped_gpu_hours: 'GPU–Pod 연결 관측 시간',
  observed_namespace_hours: 'Namespace별 GPU–Pod 연결 관측 시간',
  current_allocated_gpu: '독점 할당 GPU (기간 종료 시점)',
  allocated_gpu_hours: '독점 할당 시간',
  allocated_instance_hours: 'MIG 인스턴스 할당 시간',
  allocation_group: '그룹별 독점 할당 시간',
  vram: '평균 GPU 메모리 사용량',
  temperature: '평균 GPU 온도',
  gpu_energy: '관측 GPU 에너지',
  incident_count: '사건 수',
  total_coverage: '전체 관측률',
  observed_healthy_collection_seconds: '정상 수집 관측 시간',
};
const reasons: Record<string, string> = {
  shared_gpu_attribution_unverified:
    'GPU 공유 구간은 Namespace별 활동률을 구분할 수 없어 제외했습니다.',
  gpu_activity_identity_unverified:
    '활동 자료의 GPU·Pod 신원 또는 MIG 여부가 확인되지 않아 제외했습니다.',
  gpu_activity_missing: '연결은 관측됐지만 활동 자료가 없는 구간은 평균에서 제외했습니다.',
  source_unit_unverified: '원본 지표의 단위를 확인하지 못했습니다.',
  invalid_gpu_activity: '활동률이 유효 범위(0~100%)를 벗어났습니다.',
  conflicting_gpu_activity: '같은 GPU·시간의 활동값이 충돌해 해당 구간을 제외했습니다.',
  gpu_model_comparison_unverified: 'GPU 모델이 다르거나 확인되지 않아 평균을 보류했습니다.',
  unattributed_gpu_observation: '일부 GPU 관측을 Namespace에 연결하지 못했습니다.',
  unsupported_group_by: '이 주제에서 지원하지 않는 집계 기준입니다.',
  group_by_not_implemented: '선택한 집계 기준의 계산은 아직 구현되지 않았습니다.',
  exclusive_episode_or_activity_missing:
    '독점 할당 구간 또는 활동 자료가 없어 저활동 시간을 판단하지 못했습니다.',
  multi_gpu_workload_history_missing:
    '같은 작업이 여러 GPU를 사용한 이력이 없어 편차를 계산하지 못했습니다.',
  incident_observation_denominator_missing: '사건 발생률의 기준이 되는 관측 GPU시간이 없습니다.',
  incident_time_mapping_missing: '사건 당시 GPU와 작업의 연결 이력이 없습니다.',
  verified_workload_disruption_evidence: '작업 중단 여부를 확인할 근거가 없습니다.',
  scheduler_capacity_binding_evidence_missing: '스케줄러의 요청·용량·배치 연결 근거가 없습니다.',
  actual_power_original_samples_missing:
    '실제 소비전력 원본 표본이 없어 에너지를 계산하지 못했습니다.',
  performed_action_and_comparison_required: '수행한 조치 기록과 비교 기간이 필요합니다.',
  comparable_workload_and_causal_evidence:
    '동일 조건의 작업과 조치 효과를 확인할 근거가 필요합니다.',
  workload_purpose_unverified: '작업 목적을 확인하기 전까지 판단을 보류합니다.',
  workload_exception_review: '초기화·체크포인트·추론 대기·예약 목적을 확인하세요.',
  model_not_configured: '보고서 설명용 모델이 설정되지 않아 AI 설명을 생략했습니다.',
  no_verified_facts: '설명할 수 있는 검증된 사실이 없어 AI 설명을 생략했습니다.',
  llm_token_budget_exhausted:
    'AI 설명 입력이 허용된 토큰 예산을 초과해 모델에 요청하지 못했습니다.',
  llm_deadline_exhausted: '남은 실행시간이 없어 AI 설명을 요청하지 못했습니다.',
  llm_http_error: '모델 서버가 오류 응답을 반환해 AI 설명을 생성하지 못했습니다.',
  llm_output_truncated: '모델 출력이 길이 제한으로 잘려 AI 설명을 사용하지 않았습니다.',
  llm_invalid_output: '모델 응답이 보고서의 근거 참조 형식에 맞지 않아 사용하지 않았습니다.',
  discovery_budget_exhausted: '데이터소스 탐색 횟수 제한에 도달했습니다.',
  discovery_deadline_exhausted: '데이터소스 탐색 중 실행시간 제한에 도달했습니다.',
  range_budget_exhausted: '요청한 기간이 허용된 조회 범위를 초과했습니다.',

  allocation_contract_missing: '독점·공유·MIG 할당 이력이 없어 정확한 할당량을 확정할 수 없습니다.',
  allocation_mode_unverified: '독점·공유·MIG 할당 방식을 확인할 수 없습니다.',
  gpu_pod_identity_missing: 'GPU는 관측됐지만 같은 시점의 Pod 고유 ID를 연결하지 못했습니다.',
  observed_mapping_not_exclusive_allocation:
    'GPU–Pod 연결 관측 시간은 독점 할당량이나 실제 연산 시간이 아닙니다. 공유 GPU는 Namespace 간 중복될 수 있습니다.',
  project_owner_mapping: '프로젝트·소유자 연결 정보가 없어 Namespace 기준으로만 표시합니다.',
  required_data_missing: '이 항목의 계산에 필요한 원본 데이터 또는 식별 정보가 없습니다.',
  MIG_history_missing:
    'MIG 인스턴스 이력이 없어 계산하지 않았습니다. MIG 미사용 여부는 확인되지 않았습니다.',
  incomplete_observation:
    '일부 조회 결과가 제한되거나 실패했습니다. 수집 근거에서 확인할 수 있습니다.',
  row_limit_or_source_warning: '조회 응답이 수집량 제한에 걸렸거나 원본에서 경고를 반환했습니다.',
  sample_limit_exceeded: '최소 조회 구간에서도 수집량 제한을 초과했습니다.',
  response_byte_limit: '조회 응답 크기가 제한을 초과했습니다.',
  source_warning: '데이터소스가 불완전한 결과라는 경고를 반환했습니다.',
  collection_plan_budget_exceeded:
    '수집 전 검사에서 기간·대상에 필요한 초기 조회량이 보고서 한도를 초과했습니다.',
  collection_query_unconfigured: '요청한 분석에 필요한 조회 정의가 설정되지 않았습니다.',
  collection_task_budget_exhausted:
    '다른 필수 자료의 예산을 보존하기 위해 이 조회의 수집을 중단했습니다.',
  collection_task_deadline_exhausted:
    '이 조회에 배분한 실행시간이 끝나 남은 구간을 수집하지 못했습니다.',
  budget_exhausted: '조회 횟수 또는 실행시간 제한으로 남은 구간을 수집하지 못했습니다.',
  query_failed: '데이터 조회가 실패했습니다.',
  inventory_completeness_and_change_events:
    '전체 장비 목록과 변경 이력이 없어 관측된 장비만 표시합니다.',
  expected_inventory_denominator_missing:
    '전체 기대 대상 목록이 없어 전체 관측률을 계산하지 않았습니다.',
};
export const reportReason = (value: string) => reasons[value] || value;
export const metricName = (id: string) => names[id.split('.')[1]] || id;
export const topicName = (id: string) => topics[Number(id.slice(1)) - 1] || id;
export function metricValue(metric: Row) {
  if (metric.value == null) return '산출 불가';
  if (typeof metric.value !== 'number') return String(metric.value);
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 }).format(
    metric.unit === 'bytes' ? metric.value / byteScale(metric.value) : metric.value,
  );
}
export function metricTarget(metric: Row) {
  const target = obj(metric.target);
  return (
    [
      str(target.cluster_id),
      str(target.namespace),
      str(target.project),
      str(target.gpu_uuid),
      str(target.pod_uid),
    ]
      .filter(Boolean)
      .join(' · ') || '선택한 전체 범위'
  );
}
export function reportObservations(result: Row) {
  const groups = new Map<string, Row>();
  for (const topic of rows(result.topics)) {
    // A query can serve multiple topics. Keep one set of chunks per query/cluster.
    const local = new Map<string, Row>();
    for (const observation of rows(obj(topic.quality).observations)) {
      const key = `${str(observation.query_id)}:${str(observation.cluster_id)}`;
      const previous = local.get(key);
      const statuses = new Set([
        ...(previous ? strings(previous.statuses) : []),
        str(observation.tool_status),
      ]);
      const why = new Set(
        [...(previous ? strings(previous.reasons) : []), str(observation.reason)].filter(Boolean),
      );
      local.set(key, {
        ...observation,
        statuses: [...statuses],
        reasons: [...why],
        sample_count:
          typeof observation.sample_count === 'number' &&
          (!previous || typeof previous.sample_count === 'number')
            ? Number(previous?.sample_count ?? 0) + observation.sample_count
            : null,
      });
    }
    for (const [key, value] of local) groups.set(key, value);
  }
  return [...groups.values()];
}

function byteScale(value: number) {
  return value >= 1024 ** 3 ? 1024 ** 3 : value >= 1024 ** 2 ? 1024 ** 2 : value >= 1024 ? 1024 : 1;
}
export function metricUnit(metric: Row) {
  if (metric.unit === 'bytes' && typeof metric.value === 'number') {
    return ({ 1: 'B', 1024: 'KiB', 1048576: 'MiB', 1073741824: 'GiB' } as Record<number, string>)[
      byteScale(metric.value)
    ];
  }
  return (
    (
      {
        physical_gpu: '대',
        'GPU-hours': 'GPU·시간',
        'instance-hours': '인스턴스시간',
        percent: '%',
        percentage_points: '%p',
        events: '건',
        relations: '건',
        'events/1000 GPU-hours': '건/1,000 GPU시간',
        'target-seconds': '대상·초',
        ratio: '비율',
      } as Record<string, string>
    )[str(metric.unit)] || str(metric.unit)
  );
}
export function collectionStatus(observation: Row) {
  const reasons = strings(observation.reasons);
  const limited = reasons.some((reason) =>
    [
      'budget_exhausted',
      'discovery_budget_exhausted',
      'discovery_deadline_exhausted',
      'range_budget_exhausted',
      'collection_plan_budget_exceeded',
      'collection_task_budget_exhausted',
      'collection_task_deadline_exhausted',
    ].includes(reason),
  );
  if (limited && typeof observation.sample_count !== 'number')
    return '실행 제한 · 수집량 기록 없음';
  if (limited)
    return Number(observation.sample_count) > 0
      ? '일부 수집 후 제한으로 중단'
      : '실행 제한으로 미수집';
  if (reasons.includes('query_failed')) return '조회 실패';
  return (
    strings(observation.statuses)
      .map(
        (status) =>
          (
            ({
              ok: '수집 완료',
              empty: '해당 기간 데이터 없음',
              partial: '일부 수집',
              unavailable: '수집 불가',
              parse_error: '응답 해석 실패',
            }) as Record<string, string>
          )[status] || status,
      )
      .join(', ') || '수집 상태 기록 없음'
  );
}
export function groupLabel(groups: unknown) {
  return (
    strings(groups)
      .map(
        (group) =>
          (
            ({
              cluster: '클러스터',
              namespace: 'Namespace',
              model: 'GPU 모델',
              node: '노드',
              pod: 'Pod',
              workload: '작업',
            }) as Record<string, string>
          )[group] || group,
      )
      .join(' + ') || '기록 없음'
  );
}
export function namespaceRows(metrics: Row[]) {
  const groups = new Map<string, { target: Row; metrics: Record<string, Row> }>();
  for (const metric of metrics) {
    const name = str(metric.id).split('.')[1];
    if (
      ![
        'namespace_connected_gpu_count',
        'observed_namespace_hours',
        'namespace_activity_valid_hours',
        'namespace_connected_gpu_util',
      ].includes(name)
    )
      continue;
    const target = obj(metric.target);
    const key = JSON.stringify([target.cluster_id, target.namespace]);
    const group = groups.get(key) || { target, metrics: {} };
    group.metrics[name] = metric;
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function collectionNextCheck(observation: Row) {
  const reasons = strings(observation.reasons);
  if (
    reasons.some(
      (reason) =>
        reason.includes('budget_exhausted') ||
        reason.endsWith('deadline_exhausted') ||
        reason === 'collection_plan_budget_exceeded',
    )
  )
    return '조회·시간 한도와 분석 범위를 확인하세요. 범위 축소 또는 수집 계획 검토가 필요합니다.';
  if (
    reasons.includes('query_failed') ||
    strings(observation.statuses).some((s) => ['unavailable', 'parse_error'].includes(s))
  )
    return '관련 근거에서 오류와 데이터소스 연결·권한·응답 형식을 확인하세요.';
  if (strings(observation.statuses).includes('empty'))
    return '해당 기간·대상·지표의 표본과 필터를 확인하세요. 전체 서버에 데이터가 없다는 뜻은 아닙니다.';
  if (strings(observation.statuses).includes('partial'))
    return '누락된 조회 구간과 응답 제한·원본 경고를 확인하세요.';
  if (strings(observation.statuses).includes('ok'))
    return '수집 응답은 정상입니다. 계산 보류가 있다면 신원 연결·단위·분모 등 계산 조건을 확인하세요.';
  return '관련 근거에서 수집 상태를 확인하세요. 기록만으로 실행 여부를 단정할 수 없습니다.';
}

export function queryName(id: string) {
  return (rcaLabels.queries as Record<string, string>)[id] || '조회 의미 미확인';
}
