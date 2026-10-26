import { useSearchParams } from 'react-router-dom';
import { Panel } from '../components/ui';
import { QueryState } from '../components/live';
import {
  DeviceTable,
  IncidentHead,
  IncidentRow,
  WINDOW_DAYS,
  dateTime,
  useRecentIncidents,
} from '../components/IncidentOverview';
import {
  dayKey,
  deviceRepeats,
  windowDays,
  type DeviceKind,
  type IncidentView,
} from '../lib/incidentOverview';

const PERIODS = [
  ['1', '오늘'],
  ['7', '7일'],
  [String(WINDOW_DAYS), `${WINDOW_DAYS}일`],
] as const;
const KINDS: [string, string][] = [
  ['', '전체'],
  ['gpu', 'GPU'],
  ['switch', 'NVSwitch'],
  ['host', '서버'],
];

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
    view = params.get('view') === 'device' ? 'device' : 'time';
  const days = windowDays(now, Number(period));
  const today = dayKey(now);
  const scoped = views.filter(
    (v) =>
      (!node || v.node === node) &&
      (!kind || v.kind === (kind as DeviceKind)) &&
      days.includes(dayKey(v.at)) &&
      (!device || v.deviceKey === device),
  );
  const repeats = deviceRepeats(scoped, days);
  const hot = new Set(repeats.filter((d) => d.count >= 3).map((d) => d.key));
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
  let lastDay = '';
  return (
    <div className="page oh-page">
      <div className="oh-head-row">
        <div>
          <div className="oh-eyebrow">GPU OPERATIONS</div>
          <h1 tabIndex={-1}>사건 · RCA</h1>
          <p className="oh-sub">
            알림이 들어온 장애와 RCA 보고서를 한 줄에서 봅니다. 최근 {WINDOW_DAYS}일 · 기준{' '}
            {dateTime(now)} KST
          </p>
        </div>
      </div>
      <div className="oh-chips">
        {chips.map(([key, label, count, tone]) => (
          <button
            key={label}
            className={`oh-chip ${tone}`}
            aria-pressed={focus === key}
            onClick={() => set('focus', focus === key ? '' : key)}
          >
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
          options={PERIODS.map(([v, l]): [string, string] => [v, l])}
          onChange={(v) => set('period', v === String(WINDOW_DAYS) ? '' : v)}
        />
        보기
        <Seg
          value={view}
          options={[
            ['time', '시간순'],
            ['device', '장치별'],
          ]}
          onChange={(v) => set('view', v === 'time' ? '' : v)}
        />
        {selectedDevice && (
          <button className="oh-chip" aria-pressed="true" onClick={() => set('device', '')}>
            장치: {selectedDevice.node} {selectedDevice.device || selectedDevice.codeText} ✕
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
        {view === 'device' ? (
          <Panel
            title={`같은 장치 반복 (최근 ${period}일)`}
            description="같은 GPU·NVSwitch에서 반복되면 런북의 '공급사 전달' 단계 근거가 됩니다. 막대는 하루 단위 발생 수입니다."
          >
            <div className="oh-pad">
              <DeviceTable
                items={repeats}
                onSelect={(key) => {
                  const next = new URLSearchParams(params);
                  next.set('device', key);
                  next.delete('view');
                  setParams(next, { replace: true });
                }}
              />
            </div>
          </Panel>
        ) : (
          <>
            {stale.length > 0 && (
              <details className="oh-stale">
                <summary>
                  확인 필요 {stale.length}건 — 해제 신호 없이 하루 넘게 '발생 중'으로 남은 사건
                  (Grafana 알림 상태와 대조)
                </summary>
                {stale.map((v) => (
                  <IncidentRow key={v.id} v={v} now={now} />
                ))}
              </details>
            )}
            <IncidentHead />
            {live.map((v) => {
              const day = dayKey(v.at);
              const heading = day !== lastDay;
              lastDay = day;
              return (
                <div key={v.id}>
                  {heading && (
                    <div className="oh-day">
                      {day === today ? '오늘 ' : ''}
                      {day.slice(5)}
                    </div>
                  )}
                  <IncidentRow v={v} now={now} />
                </div>
              );
            })}
          </>
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
