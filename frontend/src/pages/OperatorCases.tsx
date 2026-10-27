import { useSearchParams } from 'react-router-dom';
import { QueryState } from '../components/live';
import { RangeCalendar } from '../components/RangeCalendar';
import {
  IncidentHead,
  IncidentRow,
  WINDOW_DAYS,
  useRecentIncidents,
} from '../components/IncidentOverview';
import {
  dateTimeText,
  dayKey,
  dayRange,
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
  ['30', '30일'],
  ['all', '전체'],
];
const DAY = /^\d{4}-\d{2}-\d{2}$/;
// Date order pages by incident; device or error order pages whole groups.
const PAGE = 50,
  GROUP_PAGE = 20;
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
  const update = (values: Record<string, string>) => {
    const next = new URLSearchParams(params);
    // Any filter change starts again from the first page.
    if (!('page' in values)) next.delete('page');
    Object.entries(values).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key),
    );
    setParams(next, { replace: true });
  };
  const set = (key: string, value: string) => update({ [key]: value });
  const picked = DAY.test(params.get('from') || '') ? params.get('from')! : '',
    pickedTo = DAY.test(params.get('to') || '') ? params.get('to')! : '';
  const period = picked
    ? ''
    : PERIODS.find((p) => p[0] === params.get('period'))?.[0] || String(WINDOW_DAYS);
  const first = picked || (period === 'all' ? null : windowDays(new Date(), Number(period))[0]);
  const last = picked ? (pickedTo > picked ? pickedTo : picked) : undefined;
  const { query, views, now, truncated } = useRecentIncidents(first, last);
  const node = params.get('node') || '',
    kind = params.get('kind') || '',
    focus = params.get('focus') || '',
    device = params.get('device') || '',
    sort = params.get('sort') || '';
  const today = dayKey(now);
  const oldest = views.length ? dayKey(views[views.length - 1].at) : today;
  const days = dayRange(first || oldest, last || today);
  const rangeText = picked
    ? picked === last
      ? fullDate(picked)
      : `${fullDate(picked)} ~ ${fullDate(last!)}`
    : period === 'all'
      ? '전체 기간'
      : period === '1'
        ? `오늘 · ${fullDate(today)}`
        : `최근 ${period}일`;
  // The Backend filters by occurrence day; the rest narrows what was loaded.
  const scoped = views.filter(
    (v) =>
      (!node || v.node === node) &&
      (!kind || v.kind === (kind as DeviceKind)) &&
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
  const ordered = sort === 'old' ? [...live].reverse() : live;
  const byGroup = sort === 'device' || sort === 'error';
  const allGroups = byGroup ? groupIncidents(ordered, sort, today) : [];
  const size = byGroup ? GROUP_PAGE : PAGE,
    total = byGroup ? allGroups.length : ordered.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const page = Math.min(pages, Math.max(1, Math.floor(Number(params.get('page'))) || 1));
  const offset = (page - 1) * size;
  const groups = byGroup
    ? allGroups.slice(offset, offset + size)
    : groupIncidents(ordered.slice(offset, offset + size), sort, today);
  const goTo = (p: number) => {
    update({ page: p > 1 ? String(p) : '' });
    window.scrollTo(0, 0);
  };
  const chips: [string, string, number, string][] = [
    ['firing', '발생 중', scoped.filter(focusTest.firing).length, 'red'],
    ['stale', '확인 필요', scoped.filter(focusTest.stale).length, 'amber'],
    ['', '조회 기간 전체', scoped.length, ''],
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
          <h1 tabIndex={-1}>RCA 조사</h1>
          <p className="oh-sub">
            알림이 들어온 장애와 RCA 장애 보고서를 한 줄에서 봅니다. 제목을 누르면 보고서가
            열립니다. {rangeText} · 기준 {dateTimeText(now)} KST
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
        <RangeCalendar
          first={first || oldest}
          last={last || today}
          today={today}
          label={rangeText}
          onChange={(from, to) => update({ from, to: to === from ? '' : to, period: '' })}
        />
        <Seg
          value={period}
          options={PERIODS}
          onChange={(v) => update({ period: v === String(WINDOW_DAYS) ? '' : v, from: '', to: '' })}
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
        emptyDescription={`${rangeText} 중 선택한 조건의 사건이 없습니다.`}
      >
        {truncated && (
          <p className="muted">
            사건이 많아 최근 일부만 불러왔습니다. 달력에서 기간을 좁혀 확인하세요.
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
        {total > 0 && (
          <nav className="oh-pager" aria-label="사건 목록 페이지">
            <small>
              {offset + 1}–{Math.min(offset + size, total)} / {total}
              {byGroup ? '개 묶음' : '건'} · 페이지당 {size}
              {byGroup ? '개 묶음' : '건'}
            </small>
            <span className="oh-seg">
              <button aria-label="이전 페이지" disabled={page === 1} onClick={() => goTo(page - 1)}>
                ‹
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  aria-pressed={p === page}
                  aria-current={p === page ? 'page' : undefined}
                  onClick={() => goTo(p)}
                >
                  {p}
                </button>
              ))}
              <button
                aria-label="다음 페이지"
                disabled={page === pages}
                onClick={() => goTo(page + 1)}
              >
                ›
              </button>
            </span>
          </nav>
        )}
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
