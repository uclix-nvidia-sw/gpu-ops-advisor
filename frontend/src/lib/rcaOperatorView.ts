// Deterministic operator view of a stored RCA result. It only restates collected
// evidence; wording marks estimates and never turns missing data into health.
import { obj, rows, str, num, strings, type Row } from './live';
import { formatRcaTime as fmt } from './rcaTime';

export type Tone = 'alert' | 'warn' | 'ok' | 'unknown';
export const toneLabels: Record<Tone, string> = {
  alert: '즉시 확인',
  warn: '주의',
  ok: '특이 변화 없음',
  unknown: '판단 보류',
};

export interface Finding {
  key: string;
  question: string;
  tone: Tone;
  verdict: string;
  /** Badge text when the generic tone label would misread, e.g. identity match. */
  label?: string;
  points: string[];
  refs: string[];
}
export interface Window {
  min: number;
  max: number;
  last: number;
  samples: number;
  first: string;
  end: string;
}
export interface MetricRow {
  name: string;
  /** Short verdict word shown first: 멈춤, 끊김, 판단 보류, 변화 없음 … */
  tag: string;
  /** One-line plain reading for the table and Q3. */
  short: string;
  unit: string;
  kind: string;
  gpus: string[];
  /** GPU UUIDs behind `gpus`, for per-GPU grouping. */
  uuids: string[];
  /** Last value before → last value after, or a word when there is no pair. */
  change: string;
  before: Window | null;
  after: Window | null;
  whole: Window | null;
  samples: number;
  lastSample: string;
  tone: Tone;
  reading: string;
  refs: string[];
}
export interface TimelineItem {
  at: string;
  label: string;
  tone: Tone;
}
export interface DeviceCount {
  label: string;
  count: number;
  current: boolean;
}

const units: Record<string, string> = {
  bytes_per_second: 'B/s',
  percent: '%',
  watts: 'W',
  enum: '상태 코드',
  state: '상태 코드',
  count: '회',
  MiB: 'MiB',
  celsius: '°C',
  bitmask: '비트마스크',
};
export const unitLabel = (unit: unknown) => units[str(unit)] || str(unit);

const fmtNum = (v: number) => String(Math.round(v * 1000) / 1000);
/** Value with its unit label; byte rates scale to KB/MB/GB per second. */
export function valueText(v: number, unit: string) {
  if (unit === 'B/s') {
    const step = (
      [
        [1e9, 'GB/s'],
        [1e6, 'MB/s'],
        [1e3, 'KB/s'],
      ] as const
    ).find(([size]) => Math.abs(v) >= size);
    if (step) return `${(v / step[0]).toFixed(1)} ${step[1]}`;
  }
  return `${fmtNum(v)} ${unit}`;
}

export function intervalLabel(ms: number) {
  if (ms < 60000) return `${Math.round(ms / 1000)}초`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}분`;
  if (ms < 86400000) return `${(ms / 3600000).toFixed(1)}시간`;
  return `${(ms / 86400000).toFixed(1)}일`;
}

const UUID = /GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/i;
/** Full PCI address with a 4-digit domain, e.g. 00000000:4E:00.0 → 0000:4e:00.0. */
export const fullPci = (v: string) =>
  v
    .toLowerCase()
    .replace(/^(nvswitch\s+)?pci:/, '')
    .replace(/^0{4}(0{4}:)/, '$1')
    .trim();
export const normPci = (v: string) =>
  v
    .toLowerCase()
    .replace(/^(nvswitch\s+)?pci:/, '')
    .replace(/^0{4,8}:/, '')
    .replace(/\.0$/, '')
    .trim();

/** Korean sentence split used to turn dense guidance into numbered lines. */
export const sentences = (text: string) =>
  text
    .split(/(?<=[다요][.])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

const t = (v: unknown) => Date.parse(str(v));
const IDLE = '사건 전부터 0';
// DCGM dcgmFabricManagerStatus_t, as quoted in the published SXID Runbook references.
const FM_STATUS: Record<number, string> = {
  0: '미지원',
  1: '시작 전',
  2: '시작 중',
  3: '성공',
  4: '실패',
  5: '인식 불가',
  6: 'NVML 버전 낮음',
};
// Lower rank reads first: alert, caution, hold, steady, idle, unchanged codes.
const rank = (m: { tone: Tone; tag: string; kind?: string }) =>
  m.tone === 'alert'
    ? 0
    : m.tone === 'warn'
      ? m.tag === '멈춤'
        ? 1
        : 1.5
      : m.tag === IDLE
        ? 4
        : m.tag === '변화 없음' && m.kind === 'enum'
          ? 5
          : m.tone === 'ok' || m.tag === '유지'
            ? 3
            : 2;
/** "NVLink 수신량" + "NVLink 송신량" → "NVLink 수신량·송신량". */
const joinNames = (names: string[]) => {
  const first = names[0]?.split(' ')[0];
  return names.length > 1 && names.every((n) => n.startsWith(`${first} `))
    ? `${first} ${names.map((n) => n.slice(first.length + 1)).join('·')}`
    : names.join('·');
};
const win = (v: unknown): Window | null => {
  const w = obj(v);
  if (typeof w.min !== 'number' || typeof w.max !== 'number') return null;
  return {
    min: w.min,
    max: w.max,
    last: num(w.last_value, NaN),
    samples: num(w.samples),
    first: str(w.first),
    end: str(w.last),
  };
};

const missingLabels: Record<string, string> = {
  event_not_found:
    '조회 구간에 커널 원본 이벤트도, 정상→오류 상태 전환도 없습니다. 오류는 구간보다 먼저 시작됐을 수 있습니다.',
  synthesis_failed: 'AI 해석 문장이 없습니다. 표와 판정은 코드로 산출한 수집 자료입니다.',
};
const aiReasons: Record<string, string> = {
  llm_http_error: 'LLM 호출 실패',
  invalid_author_response: 'LLM 응답이 형식 검사를 통과하지 못함(숫자 직접 기재 등)',
  llm_output_truncated: 'LLM 응답이 잘림',
  llm_invalid_output: 'LLM 응답을 읽을 수 없음',
  llm_token_budget_exhausted: 'LLM 토큰 예산 부족',
  llm_context_budget_exhausted: 'LLM 입력 예산 부족',
  model_not_configured: 'LLM 미설정',
};

/** Why the AI narrative is missing, read from the stored stage diagnostics. */
export function aiFailure(result: Row) {
  const quality = obj(result.quality);
  const synthesis = obj(obj(quality.analysis).synthesis);
  const writer = obj(obj(quality.report).writer);
  const code = str(synthesis.error_code) || str(writer.reason);
  const raw = synthesis.http_status ?? writer.http_status;
  const status = typeof raw === 'number' ? raw : undefined;
  // Gateway error class and limit hint recorded by the worker, never message text.
  const [errorClass, ...rest] = (str(synthesis.error_type) || str(writer.error_type)).split(':');
  const hint = rest.includes('output_tokens')
    ? '출력 토큰 한도 초과'
    : rest.includes('context_window')
      ? '입력 길이 초과'
      : '';
  const detail = [`HTTP ${status ?? '상태 미기록'}`, errorClass, hint].filter(Boolean).join(' · ');
  const reason = code
    ? `${aiReasons[code] || code}${code === 'llm_http_error' ? ` (${detail})` : ''}`
    : '';
  return { status, reason };
}

/** Merge rows of one query and GPU that exporters split by workload labels (older results). */
function mergeSeries(metricRows: Row[]) {
  const merged = new Map<string, Row>();
  const join = (a: unknown, b: unknown) => {
    const x = obj(a),
      y = obj(b);
    if (typeof x.min !== 'number') return typeof y.min === 'number' ? y : null;
    if (typeof y.min !== 'number') return x;
    const later = t(y.last) > t(x.last) ? y : x;
    return {
      min: Math.min(num(x.min), num(y.min)),
      max: Math.max(num(x.max), num(y.max)),
      samples: num(x.samples) + num(y.samples),
      first: t(y.first) < t(x.first) ? y.first : x.first,
      last: later.last,
      last_value: later.last_value,
    };
  };
  for (const m of metricRows) {
    const key = `${str(m.query_id) || str(m.name)}|${str(m.gpu_uuid)}`;
    const seen = merged.get(key);
    if (!seen) {
      merged.set(key, { ...m });
      continue;
    }
    const a = obj(seen.incident_windows),
      b = obj(m.incident_windows);
    merged.set(key, {
      ...seen,
      ...join(seen, m),
      incident_windows:
        seen.incident_windows === undefined
          ? undefined
          : {
              before: join(a.before, b.before),
              at_or_after: join(a.at_or_after || a.after, b.at_or_after || b.after),
            },
      max_sample_gap_seconds: Math.max(
        num(seen.max_sample_gap_seconds),
        num(m.max_sample_gap_seconds),
      ),
      evidence_refs: [...new Set([...strings(seen.evidence_refs), ...strings(m.evidence_refs)])],
    });
  }
  return [...merged.values()];
}

export function operatorView(result: Row) {
  const quality = obj(result.quality);
  const view = obj(quality.triage_observations);
  if (view.schema !== 'rca-triage-observations/1') return null;
  const target = obj(view.target);
  const period = obj(view.period);
  const logs = rows(view.logs);
  const periodEnd = t(period.end);
  const boundary = t(view.event_boundary);
  const codes = [...new Set(logs.map((r) => str(r.code).toLowerCase()).filter(Boolean))];
  const family = codes.some((c) => c.startsWith('sxid')) ? 'nvswitch' : 'gpu';
  const title = str(target.title);
  const alertPci = (title.match(/PCI:([0-9a-f:.]+)/i) || [])[1] || '';
  const alertUuid = (title.match(UUID) || [])[0] || '';
  const guidance = rows(quality.runbook_guidance).filter(
    (g) => g.report_applicability !== 'reference_only',
  );
  const g0 = obj(guidance[0]?.guidance);
  const checks = rows(g0.next_checks);
  const targetCheck = checks.find((c) => str(c.title).startsWith('알림이 가리키는'));
  const actionChecks = checks.filter((c) => c !== targetCheck);

  // GPU UUID → PCI slot: exporter labels first, then the node inventory report.
  const inventory = new Map<string, string>();
  rows(result.device_observations).forEach((d) =>
    rows(d.gpu_candidates).forEach((c) => {
      if (str(c.gpu_uuid) && str(c.bus_id)) inventory.set(str(c.gpu_uuid), str(c.bus_id));
    }),
  );
  const gpuInfo = new Map(rows(view.gpus).map((g) => [str(g.gpu_uuid), g]));
  gpuInfo.forEach((g, uuid) => str(g.pci_bus_id) && inventory.set(uuid, str(g.pci_bus_id)));
  const gpuLabel = (uuid: string) => {
    const bus = inventory.get(uuid);
    return bus ? `PCI ${fullPci(bus)} · ${uuid}` : uuid;
  };
  const deviceLabel = (device: string) =>
    UUID.test(device) && !/pci/i.test(device) ? gpuLabel(device) : device;

  // When: producer event time, report span and whether reports continue to the query end.
  const eventTimes = logs.flatMap((r) => strings(r.event_times)).filter((v) => !isNaN(t(v)));
  eventTimes.sort((a, b) => t(a) - t(b));
  const reportTimes = logs.flatMap((r) => [str(r.first), str(r.last)]).filter((v) => !isNaN(t(v)));
  reportTimes.sort((a, b) => t(a) - t(b));
  const firstReport = reportTimes[0] || '';
  const lastReport = reportTimes[reportTimes.length - 1] || '';
  const reports = logs.reduce((n, r) => n + num(r.reports), 0);
  const cadence =
    reports > 1 && firstReport ? (t(lastReport) - t(firstReport)) / (reports - 1) : 60000;
  const sinceLast = periodEnd - t(lastReport);
  const ongoing = !!lastReport && !isNaN(sinceLast) && sinceLast <= Math.max(120000, cadence * 2);

  const refsOf = (items: Row[]) => [...new Set(items.flatMap((r) => strings(r.evidence_refs)))];

  // 1. Device identity.
  const logDevices = [...new Set(logs.map((r) => str(r.device)).filter(Boolean))];
  const matched = alertPci && logDevices.some((d) => normPci(d) === normPci(alertPci));
  const idPoints: string[] = [];
  idPoints.push(
    `알림 장치: ${family === 'nvswitch' ? 'NVSwitch ' : ''}PCI ${alertPci || '표기 없음'}${alertUuid ? ` · ${alertUuid}` : ''}`,
  );
  idPoints.push(
    logDevices.length
      ? `오류 로그 장치: ${logDevices.map(deviceLabel).join(', ')} → ${matched ? '알림과 일치' : '알림과 다름'}`
      : '오류 로그에서 장치를 찾지 못했습니다.',
  );
  const metricRows = rows(view.metrics);
  const metricGpus = [...new Set(metricRows.map((m) => str(m.gpu_uuid)).filter(Boolean))];
  if (metricGpus.length)
    idPoints.push(
      view.metric_scope === 'node_gpu_context'
        ? `지표 범위: 같은 노드 GPU ${metricGpus.length}개 전체 — ${family === 'nvswitch' ? '스위치 자체 지표가 아니라 연결 GPU 쪽 관측입니다' : '알림 GPU만의 값이 아닙니다'}.`
        : `지표 GPU: ${metricGpus.map(gpuLabel).join(', ')} → ${alertUuid && metricGpus.every((u) => u === alertUuid) ? '알림 GPU와 같은 장치' : '알림 GPU와 대조 필요'}`,
    );
  if (alertPci && family === 'gpu') {
    const inv = [...inventory].find(([, bus]) => normPci(bus) === normPci(alertPci));
    if (inv)
      idPoints.push(
        `노드 GPU 목록에서 PCI ${fullPci(inv[1])} = ${inv[0]} (인벤토리 보고 기준, 미검증 매핑)`,
      );
  }
  rows(view.switch_pci).forEach((r) => {
    if (!strings(r.observed_pci).length)
      idPoints.push(
        `Grafana에서 스위치 PCI ${strings(r.reported_pci).join(', ')} 라벨의 시계열을 찾지 못했습니다 → NVSwitch 자체 상태는 이 보고서로 확인되지 않습니다.`,
      );
  });
  const identity: Finding = {
    key: 'identity',
    question: '알림·로그·지표가 같은 장치를 가리키나요?',
    tone: !logDevices.length || !alertPci ? 'unknown' : matched ? 'ok' : 'warn',
    verdict: !logDevices.length
      ? '오류 로그로 대상 장치를 확인하지 못했습니다. 알림 원문의 주소로 직접 대조하세요.'
      : !alertPci
        ? `알림 제목에 장치 주소가 없습니다. 오류 로그의 ${logDevices.map(deviceLabel).join(', ')}를 알림 원문과 대조하세요.`
        : matched
          ? `알림과 오류 로그가 같은 장치(PCI ${alertPci})를 가리킵니다. 이 장치를 조치 대상으로 봅니다.`
          : '알림과 오류 로그의 장치가 다릅니다. 조치 전에 장치 주소를 다시 대조하세요.',
    label: !logDevices.length || !alertPci ? '확인 필요' : matched ? '일치' : '불일치',
    points: idPoints,
    refs: refsOf(logs),
  };

  // 2. Timing and persistence. Healthy→Unhealthy reports bound the onset without kmsg.
  const onset = obj(view.onset);
  const healthyAt = str(onset.last_healthy_at);
  const unhealthyAt = str(onset.first_unhealthy_at);
  const onsetText =
    healthyAt && unhealthyAt
      ? `${fmt(healthyAt)}(마지막 정상 보고)~${fmt(unhealthyAt)}(첫 오류 보고) 사이에 시작`
      : '';
  const timePoints: string[] = [];
  timePoints.push(
    eventTimes.length
      ? `오류 발생(커널 원본 이벤트 시각): ${fmt(eventTimes[0])}`
      : onsetText
        ? `시작 구간: 커널 원본 이벤트는 수집되지 않았지만 상태 보고로 ${onsetText}했습니다.`
        : '시작 시각: 조회 구간에 커널 원본 이벤트도, 정상→오류 전환도 없습니다 — 구간보다 먼저 시작됐을 수 있습니다.',
  );
  if (eventTimes.length && onsetText) timePoints.push(`상태 보고 기준: ${onsetText}`);
  if (firstReport) timePoints.push(`첫 보고: ${fmt(firstReport)}`);
  if (lastReport)
    timePoints.push(
      `마지막 보고: ${fmt(lastReport)} ${isNaN(sinceLast) ? '' : ` (조회 종료 ${intervalLabel(sinceLast)} 전)`}`,
    );
  if (reports)
    timePoints.push(
      `보고 ${reports}건 — 같은 상태의 반복 보고이며 장애 횟수가 아닙니다${reports > 1 ? ` (약 ${intervalLabel(cadence)} 간격)` : ''}.`,
    );
  if (str(view.alert_time) && (eventTimes[0] || firstReport))
    timePoints.push(
      `알림 수신: ${fmt(str(view.alert_time))} (${eventTimes[0] ? '오류 발생' : '첫 보고'} 후 ${intervalLabel(Math.max(0, t(view.alert_time) - t(eventTimes[0] || firstReport)))})`,
    );
  const timing: Finding = {
    key: 'timing',
    question: '언제 시작됐고, 지금도 계속되나요?',
    tone: ongoing ? 'alert' : 'unknown',
    verdict: !lastReport
      ? '오류 보고 시각을 확인하지 못했습니다.'
      : ongoing
        ? `조회 종료 직전(${intervalLabel(sinceLast)} 전)까지 같은 오류가 계속 보고됐습니다. 해소됐다는 근거는 없습니다.`
        : isNaN(sinceLast)
          ? '조회 종료 시각이 없어 오류가 계속되는지 판단할 수 없습니다.'
          : `마지막 보고 뒤 ${intervalLabel(sinceLast)} 동안 추가 보고가 없습니다. 해소 여부는 후속 상태로 확인하세요.`,
    points: timePoints,
    refs: refsOf(logs),
  };

  // 3. Telemetry before/after the incident boundary, grouped when identical across GPUs.
  const groups = new Map<string, Row[]>();
  mergeSeries(metricRows).forEach((m) => {
    const key = JSON.stringify(
      [
        'name',
        'unit',
        'incident_windows',
        'min',
        'max',
        'last_value',
        'first',
        'last',
        'samples',
        'query_id',
      ].map((f) => m[f]),
    );
    groups.set(key, [...(groups.get(key) || []), m]);
  });
  const metrics: MetricRow[] = [...groups.values()].map((group) => {
    const m = group[0];
    const windows = obj(m.incident_windows);
    const before = win(windows.before);
    const after = win(windows.after) || win(windows.at_or_after);
    // Older results carry only the whole-query summary without an incident split.
    const whole = m.incident_windows === undefined ? win(m) : null;
    const u = unitLabel(m.unit);
    const enumKind = m.kind === 'enum' || ['enum', 'state', 'bitmask'].includes(str(m.unit));
    const gap = num(m.max_sample_gap_seconds) * 1000;
    const q = str(m.query_id);
    const val = (v: number) => valueText(v, u);
    const range = (w: Window) =>
      w.min === w.max
        ? val(w.min)
        : u === 'B/s'
          ? `${val(w.min)} ~ ${val(w.max)}`
          : `${fmtNum(w.min)}~${fmtNum(w.max)} ${u}`;
    const once = after?.samples === 1 ? ', 사건 뒤 표본 1회' : '';
    let tone: Tone = 'unknown';
    let tag: string;
    let short: string;
    let enumChange = '';
    if (!before && !after && !whole) {
      [tag, short] = ['자료 없음', '수치 표본이 없습니다'];
    } else if (enumKind) {
      const all = [before, after, whole].filter(Boolean) as Window[];
      const changed = all.some((w) => w.min !== w.max) || new Set(all.map((w) => w.min)).size > 1;
      const fm = q === 'D47';
      const code = (c: number) => `${fmtNum(c)}${fm && FM_STATUS[c] ? ` (${FM_STATUS[c]})` : ''}`;
      const c = all[0].min;
      if (changed) {
        enumChange =
          before && after
            ? `상태 코드 ${code(before.last)} → ${code(after.last)}`
            : '상태 코드가 바뀜';
        [tag, short] = ['변화', `${enumChange} — 원문에서 전환 시각을 확인하세요`];
        tone = 'warn';
      } else {
        enumChange = `상태 코드 ${code(c)} 유지`;
        [tag, short] = [
          '변화 없음',
          fm
            ? c === 0
              ? `${enumChange} — 이 GPU에서는 이 지표로 Fabric Manager 상태를 판단할 수 없어 FM 서비스·로그로 확인합니다`
              : enumChange
            : `${enumChange} (코드 의미는 원문 기준)`,
        ];
        tone = fm && c === 3 ? 'ok' : fm && c === 4 ? 'warn' : 'unknown';
      }
    } else if (whole) {
      [tag, short] = [
        '구분 불가',
        `조회 구간 ${range(whole)}${!isNaN(boundary) && t(whole.end) < boundary ? ' · 사건 발생 이전의 측정 기록' : ''}`,
      ];
    } else if (after && before) {
      if (after.max === 0 && before.max > 0 && before.last === 0) {
        // Already zero at the last pre-incident sample: the error did not stop it.
        tag = IDLE;
        short = `${q === 'D02' ? 'GPU가 사건 전에 이미 쉬고 있었습니다' : '사건 전에 이미 0이었습니다'} (직전 값 ${val(0)}, 사건 전 최대 ${val(before.max)})`;
      } else if (after.max === 0 && before.max > 0) {
        tag = '멈춤';
        short = `${q === 'D02' ? '작업이 멈췄습니다' : ['D33', 'D34'].includes(q) ? 'NVLink 트래픽이 멈췄습니다' : '0으로 떨어졌습니다'} (사건 전 최대 ${val(before.max)}${once})`;
        tone = 'warn';
      } else if (m.kind !== 'counter' && before.last > 0 && after.max <= before.last * 0.1) {
        // A ≥90% fall from the last pre-incident value is shown even from one sample.
        tag = '급감';
        short = `${Math.round((1 - after.max / before.last) * 100)}% 감소 (${val(before.last)} → ${val(after.last)}${once})`;
        tone = 'warn';
      } else if (
        m.kind !== 'counter' &&
        after.samples === 1 &&
        before.last > 0 &&
        Math.abs(after.last - before.last) <= before.last * 0.2
      ) {
        tag = '유지';
        short = `${val(before.last)} → ${val(after.last)} (사건 뒤 표본 1회)`;
      } else if (m.kind === 'counter' && after.max > before.max) {
        // Uncorrectable ECC growth is the decisive memory signal; other counters stay a caution.
        const dbe = ['D40', 'D42'].includes(q);
        tag = '증가';
        short = `사건 뒤 +${fmtNum(after.max - before.max)}${dbe ? ' · 정정 불가 ECC 증가 → 메모리 오류 대상' : ''}`;
        tone = dbe ? 'alert' : 'warn';
      } else if (m.kind !== 'counter' && after.samples === 1) {
        [tag, short] = [
          '판단 보류',
          `사건 뒤 1회만 수집 (${range(after)}) — 장치가 응답한다는 증거가 아닙니다`,
        ];
      } else if (m.kind === 'counter') {
        [tag, short] = ['변화 없음', `증가 없음 (${range(after)})`];
        tone = 'ok';
      } else if (before.max === 0 && after.max === 0) {
        [tag, short] = ['변화 없음', `사건 전후 모두 0 ${u}`];
        tone = 'ok';
      } else {
        [tag, short] = ['큰 변화 없음', `${range(before)} → ${range(after)}`];
        tone = 'ok';
      }
    } else if (before) {
      const quiet = periodEnd - t(before.end);
      const stopped = gap > 0 && quiet > gap * 1.5;
      const prior = before.max === 0 ? `사건 전에도 0 ${u}` : `사건 전 ${range(before)}`;
      [tag, short] = stopped
        ? ['끊김', `사건 뒤 수집이 끊겼습니다 (${prior}) — 장치 응답을 직접 확인하세요`]
        : [
            '판단 보류',
            `사건 뒤 아직 수집 전입니다 (${prior}, 수집 간격 최대 ${intervalLabel(gap || 0)})`,
          ];
      tone = stopped ? 'warn' : 'unknown';
    } else {
      [tag, short] = ['사건 후만', `사건 뒤 ${range(after!)} (사건 전 표본 없음)`];
    }
    const reading = `${short}.`;
    const change = enumKind
      ? enumChange
      : before && after
        ? `${val(before.last)} → ${val(after.last)}`
        : whole
          ? `조회 구간 ${range(whole)}`
          : after
            ? `사건 뒤 ${val(after.last)}`
            : '사건 뒤 표본 없음';
    return {
      name: str(m.name),
      tag,
      short,
      unit: u,
      kind: str(m.kind),
      gpus: group.map((r) => gpuLabel(str(r.gpu_uuid))),
      uuids: group.map((r) => str(r.gpu_uuid)),
      change,
      before,
      after,
      whole,
      samples: num(m.samples),
      lastSample: str(m.last),
      tone,
      reading,
      refs: refsOf(group),
    };
  });
  const changed = metrics.filter((m) => m.tone === 'warn' || m.tone === 'alert');
  const noAfter = metrics.filter((m) => !m.after && !m.whole);
  // Several GPUs: say which GPUs share a verdict instead of repeating each series.
  const multi =
    view.metric_scope === 'node_gpu_context' || new Set(metrics.flatMap((m) => m.uuids)).size > 1;
  const order = [...new Set(metrics.map((m) => m.name))];
  const allGpus = new Set(metrics.flatMap((m) => m.uuids));
  const gpuSet = (uuids: string[]) => {
    const unique = [...new Set(uuids)];
    const nos = unique.map((u) => str(obj(gpuInfo.get(u)).gpu_index));
    if (unique.length > 2 && unique.length === allGpus.size) return `GPU ${unique.length}개 모두`;
    return nos.every(Boolean)
      ? `GPU ${nos.sort((a, b) => Number(a) - Number(b)).join('·')}번`
      : `GPU ${unique.length}개`;
  };
  const describe = (group: MetricRow[]) => {
    if (!multi) return joinNames([...new Set(group.map((m) => m.name))]);
    const byGpu = new Map<string, string[]>();
    group.forEach((m) =>
      m.uuids.forEach((u) => byGpu.set(u, [...new Set([...(byGpu.get(u) || []), m.name])])),
    );
    const byNames = new Map<string, string[]>();
    byGpu.forEach((names, u) => {
      const key = joinNames(names.sort((a, b) => order.indexOf(a) - order.indexOf(b)));
      byNames.set(key, [...(byNames.get(key) || []), u]);
    });
    return [...byNames].map(([names, uuids]) => `${gpuSet(uuids)} ${names}`).join(', ');
  };
  const tagGroups = [
    ...metrics
      .reduce(
        (map, m) => map.set(m.tag, [...(map.get(m.tag) || []), m]),
        new Map<string, MetricRow[]>(),
      )
      .values(),
  ].sort((a, b) => rank(a[0]) - rank(b[0]));
  const withShort = (g: MetricRow[], text: string) =>
    !multi && g.length === 1 ? `${text} — ${g[0].short}` : text;
  const warnGroups = tagGroups.filter((g) => rank(g[0]) < 2);
  const idleGroups = tagGroups.filter((g) => g[0].tag === IDLE);
  const headline = [
    warnGroups.length
      ? `사건 직후 ${warnGroups.map((g) => withShort(g, `${describe(g)} ${g[0].tag}`)).join(', ')}`
      : '',
    idleGroups.length
      ? `${IDLE}: ${idleGroups.map((g) => withShort(g, describe(g))).join(', ')}`
      : '',
  ].filter(Boolean);
  // Section 3 rows: GPUs whose metrics share every verdict collapse into one row.
  const perGpu = new Map<string, MetricRow[]>();
  metrics.forEach((m) => m.uuids.forEach((u) => perGpu.set(u, [...(perGpu.get(u) || []), m])));
  const gpuGroups = new Map<string, string[]>();
  perGpu.forEach((items, u) => {
    const key = items
      .map((m) => `${m.name}:${m.tag}`)
      .sort()
      .join('|');
    gpuGroups.set(key, [...(gpuGroups.get(key) || []), u]);
  });
  const gpuRowsAll = multi
    ? [...gpuGroups.values()]
        .map((uuids) => {
          const items = uuids.flatMap((u) => perGpu.get(u) || []);
          const worst = [...items].sort((a, b) => rank(a) - rank(b))[0];
          const lines = new Map<string, string[]>();
          order.forEach((name) => {
            const values = [...new Set(items.filter((m) => m.name === name).map((m) => m.change))];
            if (!values.length) return;
            const text = values.length <= 3 ? values.join(' · ') : `GPU별 값 ${values.length}가지`;
            lines.set(text, [...(lines.get(text) || []), name]);
          });
          return {
            gpus: gpuSet(uuids),
            pci: uuids
              .map((u) => normPci(inventory.get(u) || ''))
              .filter(Boolean)
              .sort()
              .join(' · '),
            lines: [...lines].map(([text, names]) => `${joinNames(names)}: ${text}`),
            tag: worst.tag,
            tone: worst.tone,
            once:
              worst.tag !== IDLE && items.some((m) => m.after?.samples === 1 && m.kind !== 'enum'),
            rank: rank(worst),
          };
        })
        .sort((a, b) => a.rank - b.rank || a.gpus.localeCompare(b.gpus))
    : [];
  // A line every GPU row shares (e.g. an unchanged status code) is said once under the table.
  const gpuCommon =
    gpuRowsAll.length > 1
      ? gpuRowsAll[0].lines.filter((line) => gpuRowsAll.every((r) => r.lines.includes(line)))
      : [];
  const gpuRows = gpuRowsAll.map((r) => ({
    ...r,
    lines: r.lines.filter((line) => !gpuCommon.includes(line)),
  }));
  const telemetry: Finding = {
    key: 'telemetry',
    question: '사건 전후로 장치 지표는 어떻게 달라졌나요?',
    tone: !metrics.length
      ? 'unknown'
      : changed.some((m) => m.tone === 'alert')
        ? 'alert'
        : changed.length
          ? 'warn'
          : metrics.every((m) => m.after)
            ? 'ok'
            : 'unknown',
    verdict: !metrics.length
      ? '관련 지표를 수집하지 못했습니다.'
      : headline.length
        ? `${headline.join('. ')}.`
        : metrics.every((m) => m.whole)
          ? '사건 전후 구분 없이 조회 구간 요약만 있습니다. 사건 이후 장치 상태는 판단할 수 없습니다.'
          : noAfter.length === metrics.length
            ? '모든 지표가 사건 이전 표본뿐입니다. 사건 이후 장치 상태는 이 지표로 판단할 수 없습니다.'
            : '사건 전후 지표에서 뚜렷한 변화는 보이지 않습니다. 장치가 괜찮다는 판정은 아닙니다.',
    // One line per verdict; several GPUs are named by number, per-GPU values stay in section 3.
    points: multi
      ? tagGroups.map((g) => {
          const values = [...new Set(g.map((m) => m.change))];
          const detail = g[0].tag !== IDLE && values.length <= 2 ? ` — ${values.join(' · ')}` : '';
          const once = g.every((m) => m.after?.samples === 1 && m.kind !== 'enum' && m.tag !== IDLE)
            ? ' (사건 뒤 표본 1회)'
            : '';
          return `${g[0].tag}: ${describe(g)}${detail}${once}`;
        })
      : metrics.map((m) => `${m.tag}: ${m.name} — ${m.short}`),
    refs: refsOf(metricRows),
  };

  // 4. Recurrence on this device and spread across the host.
  const history = obj(quality.host_incident_history);
  const hrows = history.schema === 'rca-host-history/1' ? rows(history.rows) : [];
  const current = hrows.find((r) => r.current === true);
  const devOf = (r: Row) => str(r.device) || str(r.gpu_uuid);
  const curDev = current ? devOf(current) : '';
  const curCodes = current ? strings(current.codes) : codes;
  const sameCode = hrows.filter((r) => strings(r.codes).some((c) => curCodes.includes(c)));
  const same = sameCode.filter((r) => curDev && devOf(r) === curDev);
  const byDevice = new Map<string, number>();
  sameCode.forEach((r) => devOf(r) && byDevice.set(devOf(r), (byDevice.get(devOf(r)) || 0) + 1));
  const devices: DeviceCount[] = [...byDevice]
    .map(([d, count]) => ({ label: deviceLabel(d), count, current: d === curDev }))
    .sort((a, b) => b.count - a.count);
  const otherCodes = new Map<string, number>();
  hrows.forEach((r) =>
    strings(r.codes)
      .filter((c) => !curCodes.includes(c))
      .forEach((c) => otherCodes.set(c, (otherCodes.get(c) || 0) + 1)),
  );
  const sameTimes = same.map((r) => t(r.occurred_at)).sort((a, b) => a - b);
  const lastGap =
    sameTimes.length > 1 ? sameTimes[sameTimes.length - 1] - sameTimes[sameTimes.length - 2] : 0;
  const days = Math.round((t(obj(history.period).end) - t(obj(history.period).start)) / 86400000);
  const codeText = curCodes.map((c) => c.toUpperCase()).join(', ');
  const unit = family === 'nvswitch' ? 'NVSwitch' : 'GPU';
  const repeatPoints: string[] = [];
  if (hrows.length) {
    repeatPoints.push(
      `같은 장치·같은 오류: ${same.length}건 (이번 포함, 최근 ${days}일)${lastGap ? ` · 직전 사건과 ${intervalLabel(lastGap)} 간격` : ''}`,
    );
    repeatPoints.push(
      `같은 호스트에서 ${codeText} 오류가 난 ${unit}: ${byDevice.size}개, 사건 ${sameCode.length}건`,
    );
    if (otherCodes.size)
      repeatPoints.push(
        `같은 호스트의 다른 오류: ${[...otherCodes].map(([c, n]) => `${c.toUpperCase()} ${n}건`).join(', ')}`,
      );
    const prior = same.filter((r) => str(obj(r.prior_rca).job_id)).length;
    if (prior)
      repeatPoints.push(`같은 장치의 이전 RCA ${prior}건 — 이전 조치와 결과를 함께 비교하세요.`);
    if (same.length > 1)
      repeatPoints.push(
        '같은 장치에서 재발했습니다 — NVIDIA GPU Node Triage 기준 재발·미복구는 진단 자료를 갖춰 공급사 지원(RMA 검토)으로 넘기는 경로입니다.',
      );
    if (byDevice.size > 1)
      repeatPoints.push(
        family === 'nvswitch'
          ? `(추정) 여러 NVSwitch에서 같은 오류가 반복됩니다 — 스위치 한 개의 결함보다 Fabric Manager·베이스보드·펌웨어 같은 공통 요인을 함께 점검하세요.`
          : `(추정) 여러 GPU에서 같은 오류가 반복됩니다 — GPU 한 개의 결함보다 호스트 공통 경로(PCIe 스위치·메인보드·전원·드라이버/펌웨어)를 함께 점검하세요.`,
      );
    if ([...otherCodes.keys()].some((c) => c.split(':')[0] !== curCodes[0]?.split(':')[0]))
      repeatPoints.push(
        '(추정) GPU 오류(XID)와 NVSwitch 오류(SXID)가 같은 호스트에서 함께 반복됩니다 — 같은 시각 기준으로 연관 여부를 대조하세요. 동시 발생만으로 원인 관계를 확정하지 않습니다.',
      );
  }
  const repeat: Finding = {
    key: 'repeat',
    question: '처음인가요, 반복인가요? 다른 장치로 번졌나요?',
    tone: !hrows.length ? 'unknown' : same.length > 1 ? 'alert' : byDevice.size > 1 ? 'warn' : 'ok',
    verdict: !hrows.length
      ? '호스트 사건 이력을 조회하지 못했습니다.'
      : same.length > 1
        ? `같은 장치에서 최근 ${days}일 동안 ${same.length}번째 같은 오류입니다${lastGap ? ` (직전 ${intervalLabel(lastGap)} 전)` : ''}.${byDevice.size > 1 ? ` 같은 호스트의 다른 ${unit} ${byDevice.size - 1}개에서도 발생했습니다.` : ''}`
        : byDevice.size > 1
          ? `이 장치는 처음이지만 같은 호스트의 다른 ${unit} ${byDevice.size - 1}개에서 같은 오류가 있었습니다.`
          : `최근 ${days}일 동안 이 호스트에서 처음 등록된 ${codeText} 사건입니다.`,
    points: repeatPoints,
    refs: strings(history.evidence_refs),
  };

  // 5. Gaps an operator must fill before acting.
  const aiReason = aiFailure(result).reason;
  const gapPoints = strings(result.missing_inputs).map((c) =>
    c === 'synthesis_failed' && aiReason
      ? `${missingLabels[c]} 사유: ${aiReason}.`
      : missingLabels[c] || `미확보 자료: ${c}`,
  );
  rows(quality.collection_checks)
    .filter((c) => str(c.status) && c.status !== 'collected')
    .forEach((c) =>
      gapPoints.push(
        `${str(c.title)}: ${c.status === 'connection_required' ? '수집 경로가 연결되지 않아 조회하지 못했습니다' : `수집 상태 ${str(c.status)}`}`,
      ),
    );
  if (noAfter.length && metrics.length)
    gapPoints.push(
      `사건 이후 표본이 없는 지표 ${noAfter.length}개 — 조치 전후 상태는 직접 확인해야 합니다.`,
    );
  gapPoints.push(
    `근본 원인은 확정되지 않았습니다${str(g0.cause_note) ? ` — 원인 후보: ${str(g0.cause_note)}` : '.'}`,
  );
  // NVSwitch alerts name no GPU: take model/driver from any node GPU that reports them.
  const alertInfo = obj(
    gpuInfo.get(alertUuid) ||
      [...gpuInfo.values()].find((g) => str(g.model) || str(g.driver)) ||
      [...gpuInfo.values()][0],
  );
  gapPoints.push(
    `이 보고서에 없는 자료: ${str(alertInfo.driver) ? '' : 'OS·드라이버 버전, '}nvidia-bug-report.sh, ${family === 'nvswitch' ? 'Fabric Manager 로그, ' : ''}DCGM 진단(dcgmi diag) 결과.`,
  );
  const gaps: Finding = {
    key: 'gaps',
    question: '아직 확인되지 않은 것은 무엇인가요?',
    tone: 'unknown',
    verdict:
      result.result_status === 'partial'
        ? '일부 자료로 작성된 보고서입니다. 아래 빈칸은 조치 전에 직접 확인하세요.'
        : '아래 항목은 이 보고서로 판단할 수 없습니다.',
    points: gapPoints,
    refs: [],
  };

  const timeline: TimelineItem[] = [
    ...(healthyAt ? [{ at: healthyAt, label: '마지막 정상 상태 보고', tone: 'ok' as Tone }] : []),
    ...eventTimes.map((at) => ({
      at,
      label: '오류 발생 (커널 원본 이벤트)',
      tone: 'alert' as Tone,
    })),
    ...(firstReport ? [{ at: firstReport, label: '첫 오류 보고', tone: 'warn' as Tone }] : []),
    ...(lastReport && lastReport !== firstReport
      ? [{ at: lastReport, label: `마지막 오류 보고 (총 ${reports}건)`, tone: 'warn' as Tone }]
      : []),
    ...(str(view.alert_time)
      ? [{ at: str(view.alert_time), label: '알림 수신', tone: 'unknown' as Tone }]
      : []),
    ...metrics
      .filter((m) => m.before && !m.after && m.lastSample)
      .map((m) => ({ at: m.lastSample, label: `${m.name} 마지막 표본`, tone: 'unknown' as Tone })),
    ...(str(period.end) ? [{ at: str(period.end), label: '조회 종료', tone: 'ok' as Tone }] : []),
  ]
    .filter((i) => !isNaN(t(i.at)))
    .sort((a, b) => t(a.at) - t(b.at));

  // Pods from DCGM exporter labels across the node. A pod may hold several GPUs, so
  // pods on the alert device carry their whole GPU set; other running pods are neighbours.
  const podRows = rows(view.workloads).map((w) => ({
    gpu: str(w.gpu_uuid),
    name: [str(w.namespace), str(w.pod)].filter(Boolean).join(' / '),
    container: str(w.container),
    first: str(w.first),
    last: str(w.last),
    atIncident: !isNaN(boundary) && t(w.last) >= boundary - 120000,
  }));
  type PodRow = (typeof podRows)[number];
  const byPod = (list: PodRow[]) =>
    [
      ...list
        .reduce((pods, r) => {
          const seen = pods.get(r.name);
          return pods.set(
            r.name,
            seen
              ? {
                  ...seen,
                  first: t(r.first) < t(seen.first) ? r.first : seen.first,
                  last: t(r.last) > t(seen.last) ? r.last : seen.last,
                  atIncident: seen.atIncident || r.atIncident,
                }
              : r,
          );
        }, new Map<string, PodRow>())
        .values(),
    ].map((w) => {
      const held = [...new Set(podRows.filter((r) => r.name === w.name).map((r) => r.gpu))];
      const numbers = held
        .map((g) => str(obj(gpuInfo.get(g)).gpu_index))
        .sort((a, b) => Number(a) - Number(b));
      return {
        ...w,
        gpuCount: held.length,
        gpus: numbers.every(Boolean) ? `GPU ${numbers.join('·')}번` : `GPU ${held.length}개`,
      };
    });
  const workloads = byPod(
    podRows.filter((r) => family === 'nvswitch' || !alertUuid || r.gpu === alertUuid),
  );
  const neighbours = byPod(
    podRows.filter((r) => r.atIncident && !workloads.some((w) => w.name === r.name)),
  );

  return {
    family,
    gpuModel: str(alertInfo.model),
    driver: str(alertInfo.driver),
    gpuIndex: str(alertInfo.gpu_index),
    workloads,
    neighbours,
    onsetText,
    sameDeviceCount: same.length,
    historyDays: days,
    node: str(target.node) || str(target.k8s_node_name) || str(target.machine_id),
    cluster: str(target.cluster_id),
    codes: codes.map((c) => c.toUpperCase()),
    alertPci,
    alertUuid,
    alertGpu: alertUuid ? gpuLabel(alertUuid) : '',
    message: str(logs[0]?.message) || title,
    meaning: str(g0.meaning),
    causeNote: str(g0.cause_note),
    targetCheck,
    actionChecks,
    eventTime: eventTimes[0] || '',
    firstReport,
    lastReport,
    reports,
    ongoing,
    boundary: isNaN(boundary) ? '' : str(view.event_boundary),
    periodStart: str(period.start),
    periodEnd: str(period.end),
    findings: [identity, timing, telemetry, repeat, gaps],
    metrics,
    multiGpu: multi,
    /** Results from before pod labels were stored cannot say "no pods". */
    podsKnown: view.workload_label_source === 'dcgm_exporter_labels' || podRows.length > 0,
    gpuRows,
    gpuCommon,
    /** Headline of what changed, for the 5W "어떻게" row; empty when nothing stands out. */
    telemetryHeadline: headline.join('. '),
    timeline,
    devices,
    deviceLabel,
  };
}
export type OperatorView = NonNullable<ReturnType<typeof operatorView>>;
