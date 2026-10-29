import { useState } from 'react';
import { obj, rows, str, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';
import { Notice } from './ui';

export type NamespaceGroup = { key: string; cluster: string; namespace: string; models: Row[] };
export type NamespaceFocus = { cluster: string; namespace: string; windows: Row[]; origin: string };
// Validated categorical palette (dataviz skill: lightness band, chroma floor, CVD and normal-vision separation).
const colors = [
  '#2a78d6',
  '#eb6834',
  '#1baf7a',
  '#eda100',
  '#e87ba4',
  '#008300',
  '#6250d6',
  '#e34948',
];
const dashes = ['', '8 5', '2 4', '10 4 2 4'];

export function memoryPercent(memory: Row, field = 'used_gib_per_gpu') {
  const used = memory.used_gib_per_gpu,
    free = memory.free_gib_per_gpu;
  if (
    typeof used !== 'number' ||
    typeof free !== 'number' ||
    !Number.isFinite(used) ||
    !Number.isFinite(free) ||
    used < 0 ||
    free < 0 ||
    !Number.isFinite(used + free) ||
    used + free <= 0
  )
    return null;
  return ((field === 'free_gib_per_gpu' ? free : used) / (used + free)) * 100;
}

export function activityPoints(
  hours: Row[],
  start: number,
  end: number,
  field = 'activity_percent',
  maximum = 100,
  unit = '%',
) {
  let previousEnd = NaN;
  return [...hours]
    .sort((a, b) => str(a.start).localeCompare(str(b.start)))
    .flatMap((hour) => {
      const from = Date.parse(str(hour.start));
      const to = Date.parse(str(hour.end));
      const value = hour[field];
      if (
        !Number.isFinite(from) ||
        !Number.isFinite(to) ||
        to <= from ||
        end <= start ||
        typeof value !== 'number' ||
        !Number.isFinite(value) ||
        value < 0 ||
        value > maximum ||
        maximum <= 0
      ) {
        previousEnd = NaN;
        return [];
      }
      const point = {
        x: 48 + (((from + to) / 2 - start) / (end - start)) * 876,
        y: 220 - (value / maximum) * 180,
        move: previousEnd !== from,
        label: `${reportRequestTime(str(hour.start))} · ${value.toFixed(2)}${unit}`,
      };
      previousEnd = to;
      return [point];
    });
}

type ChartSeries = {
  key: string;
  name: string;
  color: string;
  dash: string;
  points: ReturnType<typeof activityPoints>;
  faded?: boolean;
};
function TimeChart({
  series,
  start,
  end,
  label,
  maximum = 100,
  unit = '%',
  focus,
}: {
  series: ChartSeries[];
  start: number;
  end: number;
  label: string;
  maximum?: number;
  unit?: string;
  focus?: NamespaceFocus | null;
}) {
  const [hover, setHover] = useState<number | null>(null);
  // One crosshair column per observed hour; the tooltip lists every visible series at that X.
  const columns = [...new Set(series.flatMap((s) => s.points.map((p) => Math.round(p.x))))].sort(
    (a, b) => a - b,
  );
  const hoverRows =
    hover === null
      ? []
      : series.flatMap((s) => {
          const point = s.points.find((p) => Math.round(p.x) === hover);
          return point
            ? [
                {
                  key: s.key,
                  name: s.name,
                  color: s.color,
                  dash: s.dash,
                  label: point.label,
                  y: point.y,
                },
              ]
            : [];
        });
  const hoverTime = hoverRows[0]?.label.split(' · ')[0];
  const isolated = (points: ChartSeries['points'], i: number) =>
    points[i].move && (i + 1 >= points.length || points[i + 1].move);
  return (
    <div className="aggregate-chart-frame">
      <svg
        className="aggregate-time-chart"
        viewBox="0 0 960 270"
        role="img"
        aria-label={`${label}. 색은 Namespace, 선 모양은 GPU 모델. 상세 수치는 아래에서 확인할 수 있습니다.`}
        onPointerMove={(event) => {
          if (!columns.length) return;
          const box = event.currentTarget.getBoundingClientRect();
          const x = ((event.clientX - box.left) / box.width) * 960;
          const nearest = columns.reduce((best, c) =>
            Math.abs(c - x) < Math.abs(best - x) ? c : best,
          );
          setHover(Math.abs(nearest - x) <= 30 ? nearest : null);
        }}
        onPointerLeave={() => setHover(null)}
      >
        {[0, maximum / 2, maximum].map((n) => (
          <g key={n}>
            <line
              x1="48"
              x2="924"
              y1={220 - (n / maximum) * 180}
              y2={220 - (n / maximum) * 180}
              className="aggregate-grid"
            />
            <text x="2" y={224 - (n / maximum) * 180}>
              {Number(n.toFixed(2))}
              {unit}
            </text>
          </g>
        ))}
        {focus &&
          Number.isFinite(start) &&
          end > start &&
          focus.windows.map((period, i) => {
            const a = Math.max(start, Date.parse(str(period.start))),
              b = Math.min(end, Date.parse(str(period.end)));
            return Number.isFinite(a) && Number.isFinite(b) && b > a ? (
              <rect
                key={i}
                x={48 + ((a - start) / (end - start)) * 876}
                y="30"
                width={((b - a) / (end - start)) * 876}
                height="190"
                fill="#76b900"
                fillOpacity="0.1"
              >
                <title>선택한 관측 구간</title>
              </rect>
            ) : null;
          })}
        {hover !== null && (
          <line x1={hover} x2={hover} y1="30" y2="222" className="aggregate-crosshair" />
        )}
        {series.map((s) => (
          <g key={s.key} aria-label={s.name} opacity={s.faded ? 0.18 : undefined}>
            <path
              d={s.points.map((p) => `${p.move ? 'M' : 'L'}${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeDasharray={s.dash}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {s.points.map((p, i) => (
              <circle key={`hit-${i}`} cx={p.x} cy={p.y} r="8" fill="transparent">
                <title>{`${s.name} · ${p.label}`}</title>
              </circle>
            ))}
            {s.points.map((p, i) =>
              isolated(s.points, i) || Math.round(p.x) === hover ? (
                <circle
                  key={i}
                  cx={p.x}
                  cy={p.y}
                  r="4"
                  fill={s.color}
                  className="aggregate-marker"
                />
              ) : null,
            )}
          </g>
        ))}
        {Number.isFinite(start) &&
          Number.isFinite(end) &&
          end > start &&
          [0, 0.25, 0.5, 0.75, 1].map((f) => (
            <text
              key={f}
              x={48 + 876 * f}
              y="250"
              textAnchor={f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}
            >
              {reportRequestTime(new Date(start + (end - start) * f).toISOString()).slice(0, -3)}
            </text>
          ))}
      </svg>
      {hover !== null && hoverRows.length > 0 && (
        <div
          className="aggregate-tooltip"
          role="status"
          style={{ left: `${(hover / 960) * 100}%` }}
        >
          <div className="aggregate-tooltip-time">{hoverTime}</div>
          {hoverRows.map((row) => (
            <div key={row.key}>
              <svg viewBox="0 0 20 4" aria-hidden="true">
                <line
                  x1="0"
                  x2="20"
                  y1="2"
                  y2="2"
                  stroke={row.color}
                  strokeWidth="2"
                  strokeDasharray={row.dash}
                />
              </svg>
              <strong>{row.label.split(' · ')[1]}</strong> {row.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function NamespaceCharts({
  groups,
  headingNumber = '1.2',
  hidden,
  onToggle,
  onSetCluster,
  reader = false,
  focus,
  onClearFocus,
}: {
  groups: NamespaceGroup[];
  headingNumber?: string;
  hidden: Set<string>;
  onToggle: (key: string) => void;
  onSetCluster: (keys: string[], visible: boolean) => void;
  reader?: boolean;
  focus?: NamespaceFocus | null;
  onClearFocus?: () => void;
}) {
  const [memoryFields, setMemoryFields] = useState<Record<string, string>>({});
  const hasMemory = groups.some((g) => g.models.some((r) => r.gpu_memory != null));
  const names = [...new Set(groups.map((g) => g.namespace))].sort();
  const modelNames = [
    ...new Set(groups.flatMap((g) => g.models.map((r) => str(r.gpu_model)))),
  ].sort();
  const colorOf = (name: string) => colors[names.indexOf(name) % colors.length];
  const dashOf = (model: string) =>
    dashes[modelNames.indexOf(model)] ?? `${12 + modelNames.indexOf(model) * 2} 4 2 4`;
  return (
    <div
      id={reader ? 'c2-namespace-charts' : undefined}
      tabIndex={reader ? -1 : undefined}
      className="aggregate-cluster-charts"
    >
      <h3 className="aggregate-subheading">{headingNumber}. 클러스터별 Namespace 시간대 비교</h3>
      {focus && (
        <div className="c2-chart-focus">
          <b>
            {focus.cluster} / {focus.namespace}
          </b>
          <span>선택한 대상·관측 구간 강조</span>
          <button className="button" onClick={onClearFocus}>
            강조 해제
          </button>
          <button
            className="text-link"
            onClick={() => {
              const target = document.getElementById(focus.origin);
              if (target) {
                target.tabIndex = -1;
                target.focus({ preventScroll: true });
                target.scrollIntoView({ block: 'center' });
              }
            }}
          >
            읽던 제안으로 돌아가기 ↑
          </button>
          {!groups.some((g) => g.cluster === focus.cluster && g.namespace === focus.namespace) && (
            <p>이 대상의 시간대 그래프 자료가 없습니다. 저장된 제안의 원문 근거를 확인하세요.</p>
          )}
        </div>
      )}
      <p>
        각 그래프에서 비교할 Namespace를 선택하세요. 선택은 해당 그래프에만 적용됩니다. 모두
        해제하면 선과 점만 숨겨집니다. 색은 Namespace, 선 모양은 GPU 모델이며 빈 구간은 산출
        불가입니다.
      </p>
      {[...new Set(groups.map((g) => g.cluster))].map((cluster) => {
        const clusterGroups = groups.filter((g) => g.cluster === cluster);
        const allHours = clusterGroups.flatMap((g) => g.models.flatMap((r) => rows(r.hours)));
        const start = Math.min(
          ...allHours.map((h) => Date.parse(str(h.start))).filter(Number.isFinite),
        );
        const end = Math.max(
          ...allHours.map((h) => Date.parse(str(h.end))).filter(Number.isFinite),
        );
        const memoryField = memoryFields[cluster] || 'used_gib_per_gpu';
        return (
          <section
            key={cluster}
            className="aggregate-chart"
            aria-label={`${cluster} Namespace 그래프`}
          >
            <div className="aggregate-chart-heading">
              <h4>{cluster} 클러스터</h4>
            </div>
            {(hasMemory ? ['activity', 'memory'] : ['activity']).map((metric) => {
              const isMemory = metric === 'memory';
              const title = isMemory
                ? `GPU 메모리 ${memoryField === 'used_gib_per_gpu' ? '사용' : '여유'} 비율`
                : 'GPU 활동률';
              const selectionKey = (g: NamespaceGroup) => JSON.stringify([metric, g.key]);
              const selected = clusterGroups.filter((g) => !hidden.has(selectionKey(g)));
              const series = selected.flatMap((g) =>
                g.models.map((r) => ({
                  key: JSON.stringify([g.key, r.gpu_model]),
                  name: `${g.namespace} / ${str(r.gpu_model) || '모델 미확인'}`,
                  color: colorOf(g.namespace),
                  dash: dashOf(str(r.gpu_model)),
                  faded:
                    !!focus && (g.cluster !== focus.cluster || g.namespace !== focus.namespace),
                  points: isMemory
                    ? activityPoints(
                        rows(obj(r.gpu_memory).hours).map((h) => ({
                          ...h,
                          memory_percent: memoryPercent(h, memoryField),
                        })),
                        start,
                        end,
                        'memory_percent',
                      )
                    : activityPoints(rows(r.hours), start, end),
                })),
              );
              return (
                <section
                  key={metric}
                  className="aggregate-metric-chart"
                  aria-label={`${cluster} ${isMemory ? '메모리' : '활동률'} 그래프`}
                >
                  <div className="aggregate-chart-heading">
                    <h5 className="aggregate-chart-metric-title">{title} (%)</h5>
                  </div>
                  {isMemory && (
                    <label className="aggregate-detail-selector">
                      메모리 그래프 표시
                      <select
                        value={memoryField}
                        onChange={(event) =>
                          setMemoryFields((previous) => ({
                            ...previous,
                            [cluster]: event.target.value,
                          }))
                        }
                      >
                        <option value="used_gib_per_gpu">메모리 사용 비율 (%)</option>
                        <option value="free_gib_per_gpu">메모리 여유 비율 (%)</option>
                      </select>
                    </label>
                  )}
                  {selected.length > 0 && !series.some((s) => s.points.length) && (
                    <Notice>
                      {isMemory
                        ? '선택한 Namespace에 확인된 GPU 메모리 자료가 없습니다.'
                        : '선택한 Namespace에 활동률을 계산할 수 있는 시간대가 없습니다. 하위 상세에서 자료 부족 사유를 확인하세요.'}
                    </Notice>
                  )}
                  <TimeChart
                    series={series}
                    start={start}
                    end={end}
                    label={`${cluster} Namespace별 ${title}`}
                    focus={focus?.cluster === cluster ? focus : null}
                  />
                  <div className="aggregate-chart-controls">
                    <div className="aggregate-chart-actions">
                      <button
                        type="button"
                        className="button"
                        onClick={() => onSetCluster(clusterGroups.map(selectionKey), true)}
                      >
                        전체 선택
                      </button>
                      <button
                        type="button"
                        className="button"
                        onClick={() => onSetCluster(clusterGroups.map(selectionKey), false)}
                      >
                        전체 해제
                      </button>
                    </div>
                    <fieldset className="aggregate-chart-legend">
                      <legend>
                        {selected.length
                          ? `표시할 Namespace · ${selected.length}/${clusterGroups.length} 선택`
                          : '선택 없음 · 선과 점 숨김'}
                      </legend>
                      {clusterGroups.map((g) => (
                        <label key={g.key}>
                          <input
                            type="checkbox"
                            checked={!hidden.has(selectionKey(g))}
                            onChange={() => onToggle(selectionKey(g))}
                            aria-label={`${cluster} ${g.namespace} ${title} 표시`}
                          />
                          <span
                            className="aggregate-color-key"
                            style={{ backgroundColor: colorOf(g.namespace) }}
                          />
                          <span>{g.namespace}</span>
                        </label>
                      ))}
                    </fieldset>
                    <div
                      className="aggregate-model-legend"
                      aria-label={`${cluster} ${title} 모델 선 모양`}
                    >
                      {[
                        ...new Set(
                          clusterGroups.flatMap((g) => g.models.map((r) => str(r.gpu_model))),
                        ),
                      ]
                        .sort()
                        .map((model) => (
                          <span key={model}>
                            <svg viewBox="0 0 40 12" aria-hidden="true">
                              <line
                                x1="0"
                                x2="40"
                                y1="6"
                                y2="6"
                                stroke="currentColor"
                                strokeWidth="2.5"
                                strokeDasharray={dashOf(model)}
                              />
                            </svg>
                            {model || '모델 미확인'}
                          </span>
                        ))}
                    </div>
                  </div>
                </section>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
