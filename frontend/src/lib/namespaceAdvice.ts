import { obj, rows, str, strings, type Row } from './live';

const titles: Record<string, string> = {
  capacity_review: '대기 작업에 GPU를 더 할당할지 검토',
  schedule_candidate: '작업 시작 시간을 바꿔볼지 검토',
  relative_activity: '작업 시작 시간을 나눠볼지 검토',
  queue_review: '작업이 시작되지 못한 단계 점검',
  batch_progress: '완료 기록을 다음 작업 계획에 참고할지 검토',
  resident_memory: '새 작업 배치 전 GPU 메모리 점유 확인',
  repeated_activity: '여러 시간대에 나타난 작업 대기 원인 점검',
};
// Describe the stored kind's criterion, not an additional observation or model conclusion.
const bases: Record<string, string> = {
  capacity_review:
    '높은 GPU 활동과 대기를 함께 보는 기준입니다. GPU 부족이 확인되고 부서·프로젝트 한도가 정해진 경우에만 추가 할당을 검토합니다.',
  schedule_candidate:
    '정해둔 기준보다 GPU 활동률이 낮았던 구간을 살펴봅니다. 향후 같은 네임스페이스 작업의 시작 시간을 시험할 후보이며, 빈 GPU를 뜻하지 않습니다.',
  relative_activity:
    '같은 날·같은 네임스페이스의 두 구간을 비교하는 기준입니다. 향후 일부 작업의 시작 시간을 나눠볼 시험 후보이며, 다른 날의 여유나 성능 개선은 보장하지 않습니다.',
  queue_review:
    '대기 Pod의 노드 배정과 컨테이너 시작 준비 단계를 구분하는 점검입니다. 실제 단계와 원인은 저장된 관측과 이벤트로 확인해야 합니다.',
  batch_progress:
    '완료 Job 기록과 대기 변화를 함께 보는 기준입니다. 같은 유형의 작업인지 확인해야 일정에 참고할 수 있으며, 경과시간은 순수 실행시간이나 다음 작업의 예상시간이 아닙니다.',
  resident_memory:
    '낮은 GPU 활동률과 높은 메모리 점유를 함께 보는 기준입니다. 점유 작업과 유지 목적을 확인해야 하며, 서빙·캐시나 회수 가능한 메모리로 단정하지 않습니다.',
  repeated_activity:
    '떨어진 여러 구간의 높은 GPU 활동과 대기를 살펴봅니다. 구간 사이의 상태나 GPU 부족 원인까지 확인된 것은 아닙니다.',
};

export function advicePresentation(item: Row) {
  const kind = str(item.kind);
  const observed = rows(item.observed_periods);
  const windows =
    kind === 'relative_activity'
      ? [
          { label: '비교 구간', period: obj(item.reference_period) },
          { label: '낮은 활동 구간', period: obj(item.period) },
        ]
      : kind === 'repeated_activity' && observed.length
        ? observed.map((period, i) => ({ label: `관측 구간 ${i + 1}`, period }))
        : [
            {
              label:
                kind === 'schedule_candidate'
                  ? '낮은 활동 구간'
                  : kind === 'repeated_activity'
                    ? '관측 범위 · 연속 관측 아님'
                    : '관측 구간',
              period: obj(item.period),
            },
          ];
  return {
    title: titles[kind] || str(item.recommendation, '운영 점검'),
    basis: bases[kind] || '',
    trial: ['relative_activity', 'schedule_candidate'].includes(kind),
    windows,
    models: strings(item.gpu_models),
  };
}

export function adviceGroups(advice: Row[]) {
  const clusters: {
    key: string;
    cluster: string;
    namespaces: { key: string; namespace: string; items: Row[] }[];
  }[] = [];
  // Group a reading copy; never reselect or mutate the stored advice.
  advice.forEach((item, i) => {
    const target = obj(item.target);
    const cluster = str(target.cluster_id),
      namespace = str(target.namespace);
    const key = cluster ? `known:${cluster}` : `unknown:${i}`;
    let group = clusters.find((c) => c.key === key);
    if (!group) {
      group = { key, cluster, namespaces: [] };
      clusters.push(group);
    }
    const nsKey = namespace ? `known:${namespace}` : `unknown:${i}`;
    let ns = group.namespaces.find((n) => n.key === nsKey);
    if (!ns) {
      ns = { key: nsKey, namespace, items: [] };
      group.namespaces.push(ns);
    }
    ns.items.push(item);
  });
  const byName = (a: string, b: string) => (a === b ? 0 : !a ? 1 : !b ? -1 : a < b ? -1 : 1);
  clusters.sort((a, b) => byName(a.cluster, b.cluster));
  clusters.forEach((group) => group.namespaces.sort((a, b) => byName(a.namespace, b.namespace)));
  return clusters;
}

export function adviceTime(period: Row) {
  const start = new Date(str(period.start)),
    end = new Date(str(period.end));
  if (
    !Number.isFinite(start.getTime()) ||
    !Number.isFinite(end.getTime()) ||
    end <= start ||
    ![period.start, period.end].every((v) => /(?:Z|[+-]\d{2}:\d{2})$/.test(str(v)))
  )
    return '시간 범위 미확인';
  const seconds = !!(
    start.getUTCSeconds() ||
    end.getUTCSeconds() ||
    start.getUTCMilliseconds() ||
    end.getUTCMilliseconds()
  );
  const parts = (d: Date) =>
    Object.fromEntries(
      new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        ...(seconds ? { second: '2-digit' as const } : {}),
        hourCycle: 'h23',
      })
        .formatToParts(d)
        .map((p) => [p.type, p.value]),
    );
  const a = parts(start),
    b = parts(end);
  const day = (p: Record<string, string>) => `${p.year}. ${p.month}. ${p.day}.`;
  const time = (p: Record<string, string>) =>
    `${p.hour}:${p.minute}${seconds ? ':' + p.second : ''}`;
  return `${day(a)} ${time(a)} ~ ${day(a) === day(b) ? '' : day(b) + ' '}${time(b)} KST`;
}
