import { useSearchParams } from 'react-router-dom';
import { QueryState } from '../components/live';
import {
  IncidentHead,
  IncidentRow,
  WINDOW_DAYS,
  useRecentIncidents,
} from '../components/IncidentOverview';
import {
  dateTimeText,
  dayKey,
  deviceRepeats,
  fullDate,
  kindText,
  titleText,
  windowDays,
  type DeviceKind,
  type IncidentView,
} from '../lib/incidentOverview';

const PERIODS: [string, string][] = [
  ['1', '오늘'],
  ['7', '7일'],
  [String(WINDOW_DAYS), `${WINDOW_DAYS}일`],
];
const KINDS: [string, string][] = [
  ['', '전체'],
  ['gpu', 'GPU'],
  ['switch', 'NVSwitch'],
  ['host', '서버'],
];
const SORTS: [string, string][] = [
  ['', '최신순'],
  ['old', '오래된순'],
  ['device', '장치별'],
  ['error', '오류별'],
];

interface Group {
  key: string;
  title: string;
  note: string;
  items: IncidentView[];
  showDate: boolean;
}

/** Date groups by default; device or error groups put the most frequent first. */
function groupIncidents(list: IncidentView[], sort: string, today: string): Group[] {
  const by = (key: (v: IncidentView) => string) => {
    const groups = new Map<string, IncidentView[]>();
    list.forEach((v) => groups.set(key(v), [...(groups.get(key(v)) || []), v]));
    return [...groups.entries()];
  };
  if (sort === 'device' || sort === 'error')
    return by((v) => (sort === 'device' ? v.deviceKey : v.code))
      .sort((a, b) => b[1].length - a[1].length)
      .map(([key, items]) => {
        const v = items[0];
        return {
          key,
          title:
            sort === 'device'
              ? [
                  v.node,
                  `${kindText(v.kind)} ${v.device}`.trim(),
                  titleText({ ...v, codeText: '' }),
                ].join(' · ')
              : titleText(v),
          note:
            sort === 'device'
              ? `${items.length}건 · 마지막 ${dateTimeText(v.at)}`
              : `${items.length}건 · 장치 ${new Set(items.map((i) => i.deviceKey)).size}개`,
          items,
          showDate: true,
        };
      });
  // The list is already newest- or oldest-first; date groups keep that order.
  return by((v) => dayKey(v.at)).map(([day, items]) => ({
    key: day,
    title: `${fullDate(day)}${day === today ? ' · 오늘' : ''}`,
    note: `${items.length}건`,
    items,
    showDate: false,
  }));
}

/** Classic-mode cases: one line per incident with alert state, NVIDIA action and RCA report. */
export function OperatorCases() {
  const [params, setParams] = useSearchParams();
  const { query, views, now, truncated } = useRecentIncidents();
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  const node = params.get('node') || '',
    kind = params.get('kind') || '',
    period = params.get('period') || String(WINDOW_DAYS),
    focus = params.get('focus') || '',
    device = params.get('device') || '',
    sort = params.get('sort') || '';
  const days = windowDays(now, Number(period));
  const today = dayKey(now);
  const scoped = views.filter(
    (v) =>
      (!node || v.node === node) &&
      (!kind || v.kind === (kind as DeviceKind)) &&
      days.includes(dayKey(v.at)) &&
      (!device || v.deviceKey === device),
  );
  const hot = new Set(
    deviceRepeats(scoped, days)
      .filter((d) => d.count >= 3)
      .map((d) => d.key),
  );
  const focusTest: Record<string, (v: IncidentView) => boolean> = {
    firing: (v) => v.firing && !v.stale,
    stale: (v) => v.stale,
    today: (v) => dayKey(v.at) === today,
    repeat: (v) => hot.has(v.deviceKey),
    notice: (v) => v.rca === 'notice',
  };
  const shown = focus && focusTest[focus] ? scoped.filter(focusTest[focus]) : scoped;
  const stale = shown.filter((v) => v.stale);
  const live = shown.filter((v) => !v.stale);
  const groups = groupIncidents(sort === 'old' ? [...live].reverse() : live, sort, today);
  const chips: [string, string, number, string][] = [
    ['firing', '발생 중', scoped.filter(focusTest.firing).length, 'red'],
    ['stale', '확인 필요', scoped.filter(focusTest.stale).length, 'amber'],
    ['', `전체 ${PERIODS.find((p) => p[0] === period)?.[1] || ''}`, scoped.length, ''],
    ['today', '오늘', scoped.filter(focusTest.today).length, ''],
    ['repeat', '3회 이상 반복 장치', hot.size, ''],
    ['notice', '알림만 (RCA 없음)', scoped.filter(focusTest.notice).length, ''],
  ];
  const nodes = [...new Set(views.map((v) => v.node).filter(Boolean))].sort();
  const selectedDevice = device ? views.find((v) => v.deviceKey === device) : undefined;
  return (
    <div className="page oh-page">
      <div className="oh-head-row">
        <div>
          <div className="oh-eyebrow">GPU OPERATIONS</div>
          <h1 tabIndex={-1}>사건 · RCA</h1>
          <p className="oh-sub">
            알림이 들어온 장애와 RCA 보고서를 한 줄에서 봅니다. 최근 {WINDOW_DAYS}일 · 기준{' '}
            {dateTimeText(now)} KST
          </p>
        </div>
      </div>
      <div className="oh-chips">
        {chips.map(([key, label, count, dot]) => (
          <button
            key={label}
            className="oh-chip"
            aria-pressed={focus === key}
            onClick={() => set('focus', focus === key ? '' : key)}
          >
            {dot && <i className={`oh-dot ${dot}`} />}
            {label}
            <b>{count}</b>
          </button>
        ))}
      </div>
      <div className="oh-filters">
        노드
        <Seg
          value={node}
          options={[['', '전체'], ...nodes.map((n): [string, string] => [n, n])]}
          onChange={(v) => set('node', v)}
        />
        장치
        <Seg value={kind} options={KINDS} onChange={(v) => set('kind', v)} />
        기간
        <Seg
          value={period}
          options={PERIODS}
          onChange={(v) => set('period', v === String(WINDOW_DAYS) ? '' : v)}
        />
        정렬
        <Seg value={sort} options={SORTS} onChange={(v) => set('sort', v)} />
        {selectedDevice && (
          <button className="oh-chip" aria-pressed="true" onClick={() => set('device', '')}>
            장치: {selectedDevice.node} {kindText(selectedDevice.kind)}{' '}
            {selectedDevice.device || titleText(selectedDevice)} ✕
          </button>
        )}
      </div>
      <QueryState
        query={query}
        empty={!shown.length}
        emptyTitle="조건에 맞는 사건이 없습니다."
        emptyDescription={`최근 ${WINDOW_DAYS}일 중 선택한 조건의 사건이 없습니다.`}
      >
        {truncated && (
          <p className="muted">
            사건이 많아 최근 일부만 집계했습니다. 기간이나 노드를 좁혀 확인하세요.
          </p>
        )}
        {stale.length > 0 && (
          <details className="oh-stale">
            <summary>
              <i className="oh-dot amber" />
              확인 필요 {stale.length}건 — 해제 신호 없이 하루 넘게 '발생 중'으로 남은 사건 (Grafana
              알림 상태와 대조)
            </summary>
            <div className="oh-list">
              <IncidentHead />
              {stale.map((v) => (
                <IncidentRow key={v.id} v={v} now={now} showDate />
              ))}
            </div>
          </details>
        )}
        {groups.map((g) => (
          <section key={g.key}>
            <div className="oh-group">
              <h2>{g.title}</h2>
              <small>{g.note}</small>
            </div>
            <div className="oh-list">
              <IncidentHead />
              {g.items.map((v) => (
                <IncidentRow key={v.id} v={v} now={now} showDate={g.showDate} />
              ))}
            </div>
          </section>
        ))}
      </QueryState>
    </div>
  );
}

function Seg({
  value,
  options,
  onChange,
}: {
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <span className="oh-seg">
      {options.map(([v, label]) => (
        <button key={v || 'all'} aria-pressed={value === v} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </span>
  );
}
