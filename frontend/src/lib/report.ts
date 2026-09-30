import { obj, rows, str, strings, topics, type Row } from './live';

const names: Record<string, string> = {
  observed_gpu_count: '관측된 GPU',
  observed_devices: '관측된 GPU',
  mapped_gpu_count: 'Pod 연결이 확인된 GPU',
  mapped_gpu_hours: 'GPU–Pod 연결 관측 시간',
  observed_namespace_hours: 'Namespace별 GPU–Pod 연결 관측 시간',
  namespace_activity_valid_hours: '활동률 계산에 사용한 유효 관측 시간',
  namespace_connected_gpu_util: '연결 GPU의 시간 가중 평균 활동률',
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
  group_by_not_implemented: '요청한 집계 축은 현재 계산 경로에 아직 구현되지 않았습니다.',
  unsupported_group_by: '이 주제에서 지원하지 않는 집계 기준입니다.',
  shared_gpu_attribution_unverified:
    '공유·MIG 또는 여러 Pod의 연결을 구분할 수 없어 해당 구간을 제외했습니다.',
  gpu_activity_identity_unverified:
    'GPU 활동 지표의 Pod 신원을 확인할 수 없어 해당 구간을 제외했습니다.',
  gpu_activity_missing: '연결 GPU의 활동 관측값이 부족합니다.',
  source_unit_unverified: '원본 활동 지표의 단위를 확인할 수 없습니다.',
  invalid_gpu_activity: '활동 지표가 유효한 범위를 벗어났습니다.',
  conflicting_gpu_activity: '같은 구간의 활동 관측값이 상충해 제외했습니다.',
  gpu_model_comparison_unverified:
    'GPU 모델이 다르거나 복수 GPU의 모델이 미확인이라 평균을 보류했습니다.',
  unattributed_gpu_observation: '일부 GPU 관측을 Namespace·Pod 신원에 연결하지 못했습니다.',
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
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 }).format(metric.value);
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
        sample_count: Number(previous?.sample_count || 0) + Number(observation.sample_count || 0),
      });
    }
    for (const [key, value] of local) groups.set(key, value);
  }
  return [...groups.values()];
}
