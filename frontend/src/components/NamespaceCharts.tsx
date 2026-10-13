import { rows, str, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';
import { Notice } from './ui';

export type NamespaceGroup = { key: string; cluster: string; namespace: string; models: Row[] };
const colors = [
  '#176b53',
  '#2869a5',
  '#9a4c15',
  '#7d4aa2',
  '#aa395d',
  '#487326',
  '#007c86',
  '#635837',
];
const dashes = ['', '8 5', '2 4', '10 4 2 4'];

export function activityPoints(hours: Row[], start: number, end: number) {
  let previousEnd = NaN;
  return [...hours]
    .sort((a, b) => str(a.start).localeCompare(str(b.start)))
    .flatMap((hour) => {
      const from = Date.parse(str(hour.start));
      const to = Date.parse(str(hour.end));
      const value = hour.activity_percent;
      if (
        !Number.isFinite(from) ||
        !Number.isFinite(to) ||
        to <= from ||
        end <= start ||
        typeof value !== 'number' ||
        !Number.isFinite(value) ||
        value < 0 ||
        value > 100
      ) {
        previousEnd = NaN;
        return [];
      }
      const point = {
        x: 48 + (((from + to) / 2 - start) / (end - start)) * 876,
        y: 220 - value * 1.8,
        move: previousEnd !== from,
        label: `${reportRequestTime(str(hour.start))} · ${value.toFixed(2)}%`,
      };
      previousEnd = to;
      return [point];
    });
}

export function NamespaceCharts({
  groups,
  hidden,
  onToggle,
  onSetCluster,
}: {
  groups: NamespaceGroup[];
  hidden: Set<string>;
  onToggle: (key: string) => void;
  onSetCluster: (keys: string[], visible: boolean) => void;
}) {
  const names = [...new Set(groups.map((g) => g.namespace))].sort();
  const modelNames = [
    ...new Set(groups.flatMap((g) => g.models.map((r) => str(r.gpu_model)))),
  ].sort();
  const colorOf = (name: string) => colors[names.indexOf(name) % colors.length];
  const dashOf = (model: string) =>
    dashes[modelNames.indexOf(model)] ?? `${12 + modelNames.indexOf(model) * 2} 4 2 4`;
  return (
    <div className="aggregate-cluster-charts">
      <h3>클러스터별 Namespace 시간대 비교</h3>
      <p>
        기본은 전체 Namespace입니다. 비교할 대상을 선택하세요. 모두 해제하면 선과 점이 숨겨집니다.
        색은 Namespace, 선 모양은 GPU 모델입니다. 빈 구간은 산출 불가입니다.
      </p>
      {[...new Set(groups.map((g) => g.cluster))].map((cluster) => {
        const clusterGroups = groups.filter((g) => g.cluster === cluster);
        const allHours = clusterGroups.flatMap((g) => g.models.flatMap((r) => rows(r.hours)));
        const starts = allHours.map((h) => Date.parse(str(h.start))).filter(Number.isFinite);
        const ends = allHours.map((h) => Date.parse(str(h.end))).filter(Number.isFinite);
        const start = Math.min(...starts),
          end = Math.max(...ends);
        const selected = clusterGroups.filter((g) => !hidden.has(g.key));
        const series = selected.flatMap((g) =>
          g.models.map((r) => ({
            key: JSON.stringify([g.key, r.gpu_model]),
            name: `${g.namespace} / ${str(r.gpu_model) || '모델 미확인'}`,
            color: colorOf(g.namespace),
            dash: dashOf(str(r.gpu_model)),
            points: activityPoints(rows(r.hours), start, end),
          })),
        );
        return (
          <section
            key={cluster}
            className="aggregate-chart"
            aria-label={`${cluster} Namespace 그래프`}
          >
            <div className="aggregate-chart-heading">
              <h4>{cluster} · Namespace GPU 활동률</h4>
              <div className="aggregate-chart-actions">
                <button
                  type="button"
                  className="button"
                  onClick={() =>
                    onSetCluster(
                      clusterGroups.map((g) => g.key),
                      true,
                    )
                  }
                >
                  전체 선택
                </button>
                <button
                  type="button"
                  className="button"
                  onClick={() =>
                    onSetCluster(
                      clusterGroups.map((g) => g.key),
                      false,
                    )
                  }
                >
                  전체 해제
                </button>
              </div>
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
                    checked={!hidden.has(g.key)}
                    onChange={() => onToggle(g.key)}
                    aria-label={`${cluster} ${g.namespace} 그래프 표시`}
                  />
                  <span
                    className="aggregate-color-key"
                    style={{ backgroundColor: colorOf(g.namespace) }}
                  />
                  <span>{g.namespace}</span>
                </label>
              ))}
            </fieldset>
            <div className="aggregate-model-legend" aria-label={`${cluster} GPU 모델 선 모양`}>
              {[...new Set(clusterGroups.flatMap((g) => g.models.map((r) => str(r.gpu_model))))]
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
            {selected.length > 0 && !series.some((s) => s.points.length) && (
              <Notice>
                선택한 Namespace에 활동률을 계산할 수 있는 시간대가 없습니다. 하위 상세에서 자료
                부족 사유를 확인하세요.
              </Notice>
            )}
            <svg
              className="aggregate-time-chart"
              viewBox="0 0 960 270"
              role="img"
              aria-label={`${cluster} Namespace별 GPU 활동률. 색은 Namespace, 선 모양은 GPU 모델. 상세 수치는 아래에서 확인할 수 있습니다.`}
            >
              {[0, 50, 100].map((n) => (
                <g key={n}>
                  <line
                    x1="48"
                    x2="924"
                    y1={220 - n * 1.8}
                    y2={220 - n * 1.8}
                    className="aggregate-grid"
                  />
                  <text x="2" y={224 - n * 1.8}>
                    {n}%
                  </text>
                </g>
              ))}
              {series.map((s) => (
                <g key={s.key} aria-label={s.name}>
                  <path
                    d={s.points.map((p) => `${p.move ? 'M' : 'L'}${p.x},${p.y}`).join(' ')}
                    fill="none"
                    stroke={s.color}
                    strokeWidth="2.5"
                    strokeDasharray={s.dash}
                  />
                  {s.points.map((p, i) => (
                    <circle key={i} cx={p.x} cy={p.y} r="3" fill={s.color}>
                      <title>{`${s.name} · ${p.label}`}</title>
                    </circle>
                  ))}
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
                    {reportRequestTime(new Date(start + (end - start) * f).toISOString()).slice(
                      0,
                      -3,
                    )}
                  </text>
                ))}
            </svg>
          </section>
        );
      })}
    </div>
  );
}
