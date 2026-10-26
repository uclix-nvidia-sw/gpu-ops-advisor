// Operator overview of stored incidents: what failed where, whether the alert is still
// firing, repeats on the same device and the RCA report link. Pure functions over the
// /incidents list so the cases page and the dashboard read the same numbers.
import labels from './incidentLabels.json';
import { matchedReasons } from './componentReasons';
import { obj, str, type Row } from './live';

export interface IncidentLabel {
  name: string;
  detail: string;
  action: string;
  steps: string[];
}
export type DeviceKind = 'gpu' | 'switch' | 'host';
export type RcaState = 'ready' | 'partial' | 'blocked' | 'running' | 'failed' | 'notice' | 'none';
export interface IncidentView {
  id: string;
  at: Date;
  code: string;
  codeText: string;
  label: IncidentLabel | null;
  reason: string;
  raw: string;
  node: string;
  cluster: string;
  device: string;
  kind: DeviceKind;
  deviceKey: string;
  firing: boolean;
  stale: boolean;
  resolvedAt: Date | null;
  rca: RcaState;
  jobId: string;
  nth: number;
}

const LABELS = labels as Record<string, IncidentLabel>;
// A firing alert with no resolve signal for a day is shown apart for checking against Grafana.
export const STALE_HOURS = 24;
const HOUR = 3600_000;

/** "XID 79 · GPU 접근 상실"; components show their Korean name only. */
export const titleText = (v: IncidentView) =>
  [v.codeText, v.label?.name || (v.codeText ? '런북 미등록 코드' : v.raw || '알림')]
    .filter(Boolean)
    .join(' · ');

export function incidentLabel(code: string): IncidentLabel | null {
  return LABELS[code] || null;
}

export function incidentView(record: Row, now: Date): IncidentView {
  const target = obj(record.target);
  const raw = str(target.title) || str(target.reason) || str(target.alertname);
  const named = raw.match(/\b(S?XID)[\s:]*(\d+)/i);
  const component = str(target.component);
  const code = named
    ? `${named[1].toLowerCase()}:${Number(named[2])}`
    : component
      ? `component:${component}`
      : '';
  const pci = (raw.match(/PCI:([0-9a-f:.]+)/i) || [])[1]?.toLowerCase() || '';
  const kind: DeviceKind = !pci ? 'host' : code.startsWith('sxid:') ? 'switch' : 'gpu';
  const node = str(target.k8s_node_name) || str(target.node);
  const at = new Date(str(record.occurred_at) || str(record.first_seen) || str(record.created_at));
  const firing = record.alarm_status === 'firing';
  const summary = obj(record.rca_summary);
  const published = obj(summary.latest_published);
  const job = obj(summary.latest_job);
  const notice =
    str(target.alertname) === 'GPUErrorNotice' ||
    record.rca_eligibility_reason === 'analysis_policy_unconfigured';
  const result = str(published.result_status);
  const jobStatus = str(job.status);
  const rca: RcaState =
    result === 'ready' || result === 'partial' || result === 'blocked'
      ? result
      : notice
        ? 'notice'
        : ['queued', 'running', 'retry_wait'].includes(jobStatus)
          ? 'running'
          : ['failed', 'expired', 'cancelled'].includes(jobStatus)
            ? 'failed'
            : 'none';
  const resolved = str(record.alarm_resolved_at);
  const reasons = component && !named ? matchedReasons(component, raw) : [];
  return {
    id: str(record.id),
    at,
    code,
    codeText: named ? `${named[1].toUpperCase()} ${Number(named[2])}` : '',
    label: incidentLabel(code),
    reason: reasons.map((r) => r.label).join(' · '),
    raw,
    node,
    cluster: str(target.cluster_id) || str(record.cluster_id),
    device: pci,
    kind,
    deviceKey: `${node}|${code}|${pci}`,
    firing,
    stale: firing && now.getTime() - at.getTime() > STALE_HOURS * HOUR,
    resolvedAt: resolved ? new Date(resolved) : null,
    rca,
    jobId: str(published.job_id) || str(job.job_id),
    nth: 0,
  };
}

/** Newest first; nth counts earlier incidents of the same node·code·device in the list. */
export function incidentViews(records: Row[], now: Date): IncidentView[] {
  const views = records
    .map((r) => incidentView(r, now))
    .filter((v) => !Number.isNaN(v.at.getTime()))
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  const seen = new Map<string, number>();
  views.forEach((v) => {
    v.nth = (seen.get(v.deviceKey) || 0) + 1;
    seen.set(v.deviceKey, v.nth);
  });
  return views.reverse();
}

export interface DeviceRepeat {
  key: string;
  node: string;
  code: string;
  codeText: string;
  name: string;
  device: string;
  kind: DeviceKind;
  count: number;
  last: Date;
  perDay: number[];
}

export const dayKey = (d: Date) =>
  new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(d);

/** Day keys (KST) of the window, oldest first. */
export function windowDays(now: Date, days: number) {
  return Array.from({ length: days }, (_, i) =>
    dayKey(new Date(now.getTime() - (days - 1 - i) * 24 * HOUR)),
  );
}

export function deviceRepeats(views: IncidentView[], days: string[]): DeviceRepeat[] {
  const groups = new Map<string, IncidentView[]>();
  views
    .filter((v) => v.kind !== 'host')
    .forEach((v) => groups.set(v.deviceKey, [...(groups.get(v.deviceKey) || []), v]));
  return [...groups.entries()]
    .map(([key, list]) => ({
      key,
      node: list[0].node,
      code: list[0].code,
      codeText: list[0].codeText,
      name: list[0].label?.name || '',
      device: list[0].device,
      kind: list[0].kind,
      count: list.length,
      last: list[0].at,
      perDay: days.map((d) => list.filter((v) => dayKey(v.at) === d).length),
    }))
    .sort((a, b) => b.count - a.count || b.last.getTime() - a.last.getTime());
}

// Plain impact groups so researchers and executives read the trend without XID/SXID terms.
export type Category = 'gpu' | 'link' | 'net' | 'server';
export const CATEGORIES: { key: Category; name: string; scope: string; impact: string }[] = [
  {
    key: 'gpu',
    name: 'GPU 자체',
    scope: '',
    impact: 'GPU가 사라지거나 메모리 오류 — 그 GPU를 쓰던 작업이 영향받음',
  },
  {
    key: 'link',
    name: 'GPU 간 연결',
    scope: 'NVSwitch·NVLink',
    impact: '여러 GPU를 묶은 작업의 통신이 끊길 수 있음',
  },
  {
    key: 'net',
    name: '네트워크',
    scope: 'InfiniBand·이더넷',
    impact: '노드 사이 통신·데이터 전송이 느려지거나 끊김',
  },
  {
    key: 'server',
    name: '서버',
    scope: '디스크·CPU·메모리·OS',
    impact: '노드 전체 작업에 영향 가능',
  },
];
const LINK = ['dcgm-nvlink', 'dcgm-nvswitch', 'nccl'];
const NET = ['infiniband', 'network-ethernet', 'peermem'];

export function category(v: Pick<IncidentView, 'code' | 'label'>): Category {
  if (v.code.startsWith('sxid:')) return 'link';
  if (v.code.startsWith('xid:')) return v.label?.name.includes('NVLink') ? 'link' : 'gpu';
  const component = v.code.replace(/^component:(accelerator-nvidia-)?/, '');
  if (LINK.includes(component)) return 'link';
  if (NET.includes(component)) return 'net';
  return v.code.startsWith('component:accelerator-nvidia-') ? 'gpu' : 'server';
}

export const categoryName = (key: Category) => CATEGORIES.find((c) => c.key === key)!.name;

/** "GPU 자체 3 · 서버 1": non-zero categories only. */
export function categorySummary(views: IncidentView[]) {
  return CATEGORIES.map((c) => [c.name, views.filter((v) => category(v) === c.key).length] as const)
    .filter(([, n]) => n)
    .map(([name, n]) => `${name} ${n}`)
    .join(' · ');
}

export function dailyCounts(views: IncidentView[], days: string[]) {
  return days.map((day) => {
    const today = views.filter((v) => dayKey(v.at) === day);
    return {
      day,
      counts: Object.fromEntries(
        CATEGORIES.map((c) => [c.key, today.filter((v) => category(v) === c.key).length]),
      ) as Record<Category, number>,
    };
  });
}

export function nodeStats(views: IncidentView[]) {
  const nodes = [...new Set(views.map((v) => v.node || '노드 미확인'))].sort();
  return nodes.map((node) => {
    const list = views.filter((v) => (v.node || '노드 미확인') === node);
    return {
      node,
      total: list.length,
      counts: Object.fromEntries(
        CATEGORIES.map((c) => [c.key, list.filter((v) => category(v) === c.key).length]),
      ) as Record<Category, number>,
      devices: new Set(list.filter((v) => v.kind !== 'host').map((v) => v.deviceKey)).size,
      firing: list.filter((v) => v.firing && !v.stale).length,
      stale: list.filter((v) => v.stale).length,
      last: list[0].at,
    };
  });
}

export const kindText = (kind: DeviceKind) =>
  kind === 'switch' ? 'NVSwitch' : kind === 'gpu' ? 'GPU' : '서버';

export function ago(from: Date, now: Date) {
  const minutes = Math.max(0, Math.round((now.getTime() - from.getTime()) / 60000));
  if (minutes < 60) return `${minutes}분`;
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)}시간`;
  return `${Math.round(minutes / 1440)}일`;
}
