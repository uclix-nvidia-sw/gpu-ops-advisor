import { obj, rows, str, strings, type Row } from './live';

const titles: Record<string, string> = {
  capacity_review: 'GPU 추가 할당 검토',
  schedule_candidate: '작업 시간대 시험 검토',
  relative_activity: '작업 시간대 비교·시험 검토',
  queue_review: '작업 시작 지연 점검',
  batch_progress: '배치 완료·남은 대기 점검',
  resident_memory: 'GPU 메모리 점유 점검',
  repeated_activity: '여러 시간대의 GPU 활동·대기 점검',
};
const bases: Record<string, string> = {
  capacity_review: 'GPU 활동이 높고 대기 Pod도 관측된 구간입니다.',
  schedule_candidate:
    '정해둔 낮은 활동 기준에 해당한 구간입니다. 다른 구간과의 비교 결과는 아닙니다.',
  relative_activity: '같은 날의 두 구간을 비교한 시험 후보입니다.',
  queue_review: '대기 Pod의 노드 배정과 시작 준비 상태를 구분하기 위한 점검입니다.',
  batch_progress: '해당 기간의 완료 기록과 대기 변화를 함께 봅니다.',
  resident_memory: 'GPU 활동률은 낮고 메모리 점유는 높았던 구간입니다.',
  repeated_activity:
    '여러 관측 구간의 활동과 대기를 봅니다. 구간 사이도 같은 상태였다는 뜻은 아닙니다.',
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
