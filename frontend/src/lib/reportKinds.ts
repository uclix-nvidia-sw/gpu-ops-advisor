/** Request presets only: stored topic IDs, schedules and results keep their original meaning. */
export const reportKinds = [
  {
    id: 'namespace',
    name: 'Namespace별 GPU 사용 현황',
    topicIds: ['O08'],
    groupBy: 'namespace',
    description: 'Namespace별 GPU 연결 수·시간과 평균 활동률을 확인합니다.',
    insight: '어디에서 GPU를 많이 또는 적게 사용하는지 보고 배분 정책을 검토합니다.',
    requirement: 'GPU 활동률과 같은 시각의 GPU·Pod 신원 정보가 필요합니다.',
    limit: '연결 관측이며 독점 할당량·Namespace 실사용률·회수 가능량은 아닙니다.',
  },
  {
    id: 'health',
    name: 'GPU 상태·에너지 사용·장애 현황',
    topicIds: ['O01', 'O09', 'O05'],
    groupBy: 'cluster',
    description: 'GPU 메모리·온도, 에너지 사용량과 등록된 장애 이력을 함께 확인합니다.',
    insight: '점검할 장비와 운영상 주의할 항목을 찾습니다.',
    requirement: '장비 신원·메모리·온도·실제 전력 관측과 저장된 사건 기록을 사용합니다.',
    limit:
      '에너지는 선택 범위의 관측 GPU 합계이며 클러스터별 값이 아닙니다. 장애 원인을 확정하지 않습니다.',
  },
  {
    id: 'allocation',
    name: '할당한 GPU의 활용도 점검',
    topicIds: ['O02', 'O03', 'O04'],
    groupBy: 'cluster',
    description: 'GPU 할당 시간, 낮은 활동과 같은 작업의 GPU 간 사용 편차를 살펴봅니다.',
    insight: 'GPU 배정 수나 작업 구성을 재검토할 후보를 확인합니다.',
    requirement:
      '검증된 할당 이력이 필요합니다. 저활동은 전용 할당과 연속 할당 구간 정보도 필요합니다.',
    limit:
      '연결 관측만 수집하는 설정에서는 O02 관측 수치는 남아도 O03·O04는 계산할 수 없습니다. 낮은 활동을 낭비로 단정하지 않습니다.',
  },
  {
    id: 'incident-workloads',
    name: '장애 당시 실행 작업 확인',
    topicIds: ['O06'],
    groupBy: 'cluster',
    description: '장애가 발생한 시점에 해당 GPU와 연결돼 있던 작업을 확인합니다.',
    insight: '장애 이후 어떤 작업부터 조사할지 대상을 좁힙니다.',
    requirement: '저장된 사건과 사건 당시 검증된 GPU·Pod 연결 이력이 필요합니다.',
    limit: '해당 작업의 실제 중단·피해나 장애 원인을 판정하는 보고서는 아닙니다.',
  },
  {
    id: 'waiting',
    name: 'GPU 요청 작업의 대기 현황',
    topicIds: ['O07'],
    groupBy: 'cluster',
    description: 'GPU를 요청했지만 아직 실행할 서버에 배정되지 않은 작업을 확인합니다.',
    insight: '대기 중인 GPU 요청을 파악하고 배치 상태를 점검합니다.',
    requirement: 'Pod별 유효 GPU 요청량과 미배치 상태를 확인할 수 있는 자료가 필요합니다.',
    limit:
      '대기가 곧 GPU 부족을 뜻하지는 않습니다. GPU 부족량이나 대기 원인은 별도 확인이 필요합니다.',
  },
  {
    id: 'comparison',
    name: '운영 조치 전후 비교',
    topicIds: ['O10'],
    groupBy: 'cluster',
    description: '기록된 운영 조치 전후의 관측 수치를 비교합니다.',
    insight: '조치 뒤 수치가 어떻게 달라졌는지 살펴봅니다.',
    requirement:
      '전후 비교 계산에는 수행한 조치 기록 ID와 비교 기간이 필요합니다. 종합·자동보고서에서 조건이 없으면 비교하지 않은 이유를 표시합니다.',
    limit:
      '기간·관측 범위·업무량 차이도 영향을 줍니다. 조치의 인과적 효과나 절감 성과를 확정하지 않습니다.',
  },
  {
    id: 'monitoring',
    name: '모니터링 수집 상태 점검',
    topicIds: ['O11'],
    groupBy: 'cluster',
    description: '분석 기간에 수집 대상이 정상 응답한 시간을 확인합니다.',
    insight: '모니터링 공백 때문에 해석에 주의할 범위를 확인합니다.',
    requirement:
      '수집 대상의 정상 응답 지표가 필요하며 전체 수집률에는 기대 대상·주기 정보가 필요합니다.',
    limit: '모든 보고서에 표시되는 이번 조회의 성공·실패 진단과는 별도 분석입니다.',
  },
];

export function reportKind(id: string | null) {
  return reportKinds.find((kind) => kind.id === id) || reportKinds[0];
}

export const topicDisplayBases: Record<string, string> = {
  O01: 'GPU 대수는 선택 범위 전체 · 메모리·온도는 GPU 장비별',
  O02: 'GPU 수·연결·할당 시간은 선택 범위 전체 · 상세 지표는 표시된 대상별',
  O03: '검증된 전용 할당 구간의 저활동 GPU 시간 합계',
  O04: '같은 Pod·같은 시간에 연결된 GPU 간 활동률 비교',
  O05: '선택 범위·분석 기간에 등록된 사건 기준',
  O06: '사건 발생 시점의 GPU와 Pod 관계별',
  O07: '미배치 Pod의 유효 GPU 요청량 · 선택 범위 합계',
  O08: '클러스터·Namespace별 연결 관측 · 클러스터 요약 포함',
  O09: '선택 범위 전체의 관측 GPU 에너지 합계',
  O10: '기록된 조치와 비교 기간 · 두 기간에 공통 관측된 GPU의 에너지 합계',
  O11: '수집 대상별 정상 응답 시간을 합산 · 전체 커버리지는 별도 근거 필요',
};

export function reportSelection(ids: string[]) {
  const kinds = reportKinds.filter((kind) => ids.includes(kind.id));
  const topic_ids = [...new Set(kinds.flatMap((kind) => kind.topicIds))].sort();
  return {
    topic_ids,
    group_by: topic_ids.length === 1 && topic_ids[0] === 'O08' ? ['namespace'] : ['cluster'],
    topic_group_by: Object.fromEntries(
      kinds.flatMap((kind) => kind.topicIds.map((id) => [id, [kind.groupBy]])),
    ),
  };
}
