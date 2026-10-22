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
  unit: string;
  kind: string;
  gpus: string[];
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

export function intervalLabel(ms: number) {
  if (ms < 60000) return `${Math.round(ms / 1000)}초`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}분`;
  if (ms < 86400000) return `${(ms / 3600000).toFixed(1)}시간`;
  return `${(ms / 86400000).toFixed(1)}일`;
}

const UUID = /GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/i;
/** GPU-81ec1404-9d04-… → GPU-81ec1404…; the full value stays in titles and raw evidence. */
export const shortGpu = (text: string) =>
  text.replace(/(GPU-[0-9a-f]{8})(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/gi, '$1…');
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
const fmtNum = (v: number) => String(Math.round(v * 1000) / 1000);
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
  event_not_found: '조회 구간에서 원본 오류 이벤트(발생 시각)를 찾지 못했습니다.',
  synthesis_failed: 'LLM 원인 분석이 완료되지 않아 코드로 산출한 자료만으로 작성됐습니다.',
};

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

  // GPU UUID → PCI slot from the node inventory report (unverified mapping, labelled as such).
  const inventory = new Map<string, string>();
  rows(result.device_observations).forEach((d) =>
    rows(d.gpu_candidates).forEach((c) => {
      if (str(c.gpu_uuid) && str(c.bus_id)) inventory.set(str(c.gpu_uuid), str(c.bus_id));
    }),
  );
  const gpuLabel = (uuid: string) => {
    const bus = inventory.get(uuid);
    return `${shortGpu(uuid)}${bus ? ` (PCI ${normPci(bus)})` : ''}`;
  };
  const deviceLabel = (device: string) =>
    UUID.test(device) && !/pci/i.test(device) ? gpuLabel(device) : shortGpu(device);

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
    `알림 장치: ${family === 'nvswitch' ? 'NVSwitch ' : ''}PCI ${alertPci || '표기 없음'}${alertUuid ? ` · ${gpuLabel(alertUuid)}` : ''}`,
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
        `노드 GPU 목록에서 PCI ${normPci(alertPci)} = ${shortGpu(inv[0])} (인벤토리 보고 기준, 미검증 매핑)`,
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
          ? `알림과 오류 로그가 같은 장치(PCI ${normPci(alertPci)})를 가리킵니다. 이 장치를 조치 대상으로 봅니다.`
          : '알림과 오류 로그의 장치가 다릅니다. 조치 전에 장치 주소를 다시 대조하세요.',
    label: !logDevices.length || !alertPci ? '확인 필요' : matched ? '일치' : '불일치',
    points: idPoints,
    refs: refsOf(logs),
  };

  // 2. Timing and persistence.
  const timePoints: string[] = [];
  timePoints.push(
    eventTimes.length
      ? `오류 발생(원본 이벤트 시각): ${fmt(eventTimes[0])}`
      : '원본 이벤트 시각이 조회 구간에 없습니다 — 구간 이전에 이미 발생했을 수 있습니다.',
  );
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
  metricRows.forEach((m) => {
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
    let tone: Tone = 'unknown';
    let reading: string;
    const range = (w: Window) =>
      w.min === w.max ? `${fmtNum(w.min)} ${u}` : `${fmtNum(w.min)}~${fmtNum(w.max)} ${u}`;
    if (!before && !after && !whole) reading = '수치 표본이 없습니다.';
    else if (enumKind) {
      const all = [before, after, whole].filter(Boolean) as Window[];
      const changed = all.some((w) => w.min !== w.max) || new Set(all.map((w) => w.min)).size > 1;
      reading = changed
        ? '여러 상태 코드가 관측됐습니다 — 원문에서 전환 시각을 확인하세요.'
        : `상태 코드 ${fmtNum(all[0].min)} 유지 (코드 의미는 원문 기준, 수치 크기로 비교하지 않음).`;
      tone = changed ? 'warn' : 'unknown';
    } else if (whole) {
      reading = `조회 구간 ${range(whole)} · 사건 전후 구분 정보가 없는 결과입니다.${!isNaN(boundary) && t(whole.end) < boundary ? ' 사건 발생 이전의 측정 기록입니다.' : ''}`;
    } else if (after && before) {
      if (after.max === 0 && before.max > 0) {
        reading = `사건 이후 0 ${u}로 떨어졌습니다 (사건 전 최대 ${fmtNum(before.max)} ${u}).`;
        tone = 'warn';
      } else if (m.kind === 'counter' && after.max > before.max) {
        // Uncorrectable ECC growth is the decisive memory signal; other counters stay a caution.
        const dbe = ['D40', 'D42'].includes(str(m.query_id));
        reading = `사건 이후 누적값이 ${fmtNum(after.max - before.max)} 증가했습니다.${dbe ? ' 정정 불가 ECC가 늘었으므로 해당 GPU를 메모리 오류 대상으로 봅니다.' : ''}`;
        tone = dbe ? 'alert' : 'warn';
      } else {
        reading = `사건 전 ${range(before)} → 사건 이후 ${range(after)}.`;
        tone = 'ok';
      }
    } else if (before) {
      const quiet = periodEnd - t(before.end);
      const stopped = gap > 0 && quiet > gap * 1.5;
      reading = `${m.kind === 'counter' && before.min === before.max ? `사건 전 누적값 변화 없음(${range(before)})` : before.max === 0 ? `사건 전 내내 0 ${u}` : `사건 전 ${range(before)}`}. 사건 이후 표본 없음 — ${
        stopped
          ? `수집 주기(최대 ${intervalLabel(gap)})를 넘겨 끊겼습니다. 장치 응답 여부를 직접 확인하세요.`
          : `수집 주기(최대 ${intervalLabel(gap || 0)}) 안이라 끊김으로 단정할 수 없습니다.`
      }`;
      tone = stopped ? 'warn' : 'unknown';
    } else {
      reading = `사건 이후 ${range(after!)} (사건 전 표본 없음).`;
    }
    return {
      name: str(m.name),
      unit: u,
      kind: str(m.kind),
      gpus: group.map((r) => gpuLabel(str(r.gpu_uuid))),
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
      : changed.length
        ? `${metrics.length}개 지표 중 ${changed.length}개에서 사건 전후 변화가 보입니다: ${changed.map((m) => m.name).join(', ')}.`
        : metrics.every((m) => m.whole)
          ? '사건 전후 구분 없이 조회 구간 요약만 있습니다. 사건 이후 장치 상태는 판단할 수 없습니다.'
          : noAfter.length === metrics.length
            ? '모든 지표가 사건 이전 표본뿐입니다. 사건 이후 장치 상태는 이 지표로 판단할 수 없습니다.'
            : '사건 전후 지표에서 뚜렷한 변화는 보이지 않습니다. 장치가 괜찮다는 판정은 아닙니다.',
    points: metrics.map(
      (m) =>
        `${m.name} · ${m.gpus.length > 1 ? `GPU ${m.gpus.length}개 동일` : m.gpus[0]}: ${m.reading}`,
    ),
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
  const gapPoints = strings(result.missing_inputs).map(
    (c) => missingLabels[c] || `미확보 자료: ${c}`,
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
  gapPoints.push(
    `이 보고서에 없는 자료: OS·드라이버 버전, nvidia-bug-report.sh, ${family === 'nvswitch' ? 'Fabric Manager 로그, ' : ''}DCGM 진단(dcgmi diag) 결과.`,
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
    ...eventTimes.map((at) => ({ at, label: '오류 발생 (원본 이벤트)', tone: 'alert' as Tone })),
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

  return {
    family,
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
    timeline,
    devices,
    deviceLabel,
  };
}
export type OperatorView = NonNullable<ReturnType<typeof operatorView>>;
