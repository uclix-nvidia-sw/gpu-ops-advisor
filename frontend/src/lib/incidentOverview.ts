// Operator overview of stored incidents: received alert content, device repeats
// and the RCA report link. Stored incidents do not establish current health.
// Both pages use the same pure functions over the /incidents list.
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
  rca: RcaState;
  jobId: string;
  executionStatus?: string;
  latestJobId?: string;
  publishedStatus?: string;
  publishedJobId?: string;
  nth: number;
  uuid?: string;
  component?: string;
}

const LABELS = labels as Record<string, IncidentLabel>;
const HOUR = 3600_000;

// List identity comes from the received alert, never from a Runbook translation.
export function incidentName(v: IncidentView): string {
  let text = v.raw.replace(/^\s*\[[^\]]+\]\s*/, '');
  text = text.replace(/^(?!S?XID:)[a-z][a-z0-9-]*:\s*/i, '');
  text = text.replace(/^\s*\[[^\]]+\]\s*/, '');
  if (/^s?xid:/.test(v.code)) {
    text = text.replace(/^S?XID[\s:]*\d+\s*/i, '');
    text = text.replace(/\s+detected on\b.*$/i, '').replace(/^detected on\b.*$/i, '');
    text = text.replace(/^\((.*)\)$/, '$1');
    // A received mnemonic stays verbatim unless the alert also provides prose.
    text = text.replace(/^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\s+(?=\S)/, '');
  }
  return text.trim();
}
export const titleText = (v: IncidentView) =>
  [v.codeText, incidentName(v)].filter(Boolean).join(' · ') || '알림 내용 미확인';

export function incidentLabel(code: string): IncidentLabel | null {
  return LABELS[code] || null;
}

export function incidentView(record: Row): IncidentView {
  const target = obj(record.target);
  const raw = str(target.title) || str(target.reason) || str(target.alertname);
  const named = raw.match(/\b(S?XID)[\s:]*(\d+)/i);
  const component = str(target.component);
  const code = named
    ? `${named[1].toLowerCase()}:${Number(named[2])}`
    : component
      ? `component:${component}`
      : '';
  const pci = (raw.match(/PCI:\s*([0-9a-f:.]+)/i) || [])[1] || '';
  const uuid = str(target.gpu_uuid) || raw.match(/UUID:\s*(GPU-[a-z0-9-]+)/i)?.[1] || '';
  const kind: DeviceKind =
    code.startsWith('sxid:') || component.endsWith('-sxid')
      ? 'switch'
      : code.startsWith('xid:') ||
          component.startsWith('accelerator-nvidia') ||
          uuid ||
          /\bGPU\b/i.test(raw)
        ? 'gpu'
        : 'host';
  const node = str(target.k8s_node_name) || str(target.node) || str(target.machine_id);
  const at = new Date(str(record.occurred_at) || str(record.first_seen) || str(record.created_at));
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
    device: pci || uuid,
    uuid,
    component,
    kind,
    deviceKey: JSON.stringify([
      str(target.cluster_id) || str(record.cluster_id),
      node,
      code,
      (pci || uuid).toLowerCase(),
    ]),
    rca,
    jobId: str(published.job_id) || str(job.job_id),
    executionStatus: jobStatus,
    latestJobId: str(job.job_id),
    publishedStatus: result,
    publishedJobId: str(published.job_id),
    nth: 0,
  };
}

/** Newest first; nth counts earlier incidents of the same node·code·device in the list. */
export function incidentViews(records: Row[]): IncidentView[] {
  const views = records
    .map((r) => incidentView(r))
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

const WEEKDAY = '일월화수목금토';
const weekday = (key: string) => WEEKDAY[new Date(`${key}T12:00:00+09:00`).getUTCDay()];

/** "2026.10.26. (월)" for a KST day key. */
export const fullDate = (key: string) => `${key.replaceAll('-', '.')}. (${weekday(key)})`;

/** "10.26 (월)" for chart axes. */
export const shortDate = (key: string) => `${key.slice(5).replace('-', '.')} (${weekday(key)})`;

/** "17:41" in KST. */
export const clock = (d: Date) =>
  new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(d);

/** "2026.10.26. (월) 17:41" in KST. */
export const dateTimeText = (d: Date) => `${fullDate(dayKey(d))} ${clock(d)}`;

export interface ErrorRepeat {
  code: string;
  codeText: string;
  name: string;
  kind: DeviceKind;
  count: number;
  devices: number;
  last: Date;
}

/** Repeats per error code across devices, most frequent first. */
export function errorRepeats(views: IncidentView[]): ErrorRepeat[] {
  const groups = new Map<string, IncidentView[]>();
  views
    .filter((v) => v.kind !== 'host')
    .forEach((v) => groups.set(v.code, [...(groups.get(v.code) || []), v]));
  return [...groups.values()]
    .map((list) => ({
      code: list[0].code,
      codeText: list[0].codeText,
      name: list[0].label?.name || '',
      kind: list[0].kind,
      count: list.length,
      devices: new Set(list.map((v) => v.deviceKey)).size,
      last: list.reduce((a, v) => (v.at > a ? v.at : a), list[0].at),
    }))
    .sort((a, b) => b.count - a.count || b.last.getTime() - a.last.getTime());
}

/** Day keys (KST) of the window, oldest first. */
export function windowDays(now: Date, days: number) {
  return Array.from({ length: days }, (_, i) =>
    dayKey(new Date(now.getTime() - (days - 1 - i) * 24 * HOUR)),
  );
}

/** Inclusive KST day keys from `first` to `last`. */
export function dayRange(first: string, last: string) {
  const days: string[] = [];
  for (let t = Date.parse(`${first}T12:00:00+09:00`); dayKey(new Date(t)) <= last; t += 24 * HOUR)
    days.push(dayKey(new Date(t)));
  return days;
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
      last: list.reduce((a, v) => (v.at > a ? v.at : a), list[0].at),
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
