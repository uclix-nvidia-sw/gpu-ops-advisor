import { Link } from 'react-router-dom';
import {
  CATEGORIES,
  category,
  dailyCounts,
  fullDate,
  shortDate,
  type IncidentView,
} from '../lib/incidentOverview';
import { obj, rows, str, type Row } from '../lib/live';
import { memoryPercent } from './NamespaceCharts';
import './console2-charts.css';

const categoryColors = ['#76b900', '#397fc2', '#cf8a25', '#8b6db0'];
const percent = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
const count = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;

export function IncidentCharts({
  views,
  days,
  period,
}: {
  views: IncidentView[];
  days: string[];
  period: string;
}) {
  const daily = dailyCounts(views, days);
  const counts = CATEGORIES.map((c) => views.filter((v) => category(v) === c.key).length);
  const peak = Math.max(1, ...daily.map((d) => Object.values(d.counts).reduce((a, b) => a + b, 0)));
  const top = peak <= 4 ? 4 : Math.ceil(peak / 4) * 4;
  const step = 820 / Math.max(1, days.length);
  let offset = 0;
  return (
    <div className="c2-charts-row">
      <section className="c2-chart-card" aria-labelledby="c2-trend-title">
        <header>
          <div>
            <h2 id="c2-trend-title">사건 발생 추이</h2>
            <p>유형별 수신 건수 · 날짜를 선택해 사건 확인</p>
          </div>
          <span>단위: 건 / KST</span>
        </header>
        <div className="c2-chart-legend">
          {CATEGORIES.map((c, i) => (
            <span key={c.key}>
              <i style={{ background: categoryColors[i] }} />
              {c.name}
            </span>
          ))}
        </div>
        <div className="c2-svg-scroll">
          <svg
            className="c2-trend-chart"
            viewBox="0 0 900 240"
            role="group"
            aria-label={`${period}일간 유형별 사건 발생 추이. 각 날짜에서 사건 목록으로 이동할 수 있습니다.`}
          >
            {[0, 1, 2, 3, 4].map((n) => (
              <g key={n}>
                <line
                  x1="48"
                  x2="878"
                  y1={192 - n * 40}
                  y2={192 - n * 40}
                  stroke="#e5e8e6"
                  strokeDasharray={n ? '3 4' : undefined}
                />
                <text x="36" y={197 - n * 40} textAnchor="end" fill="#66716b" fontSize="12">
                  {(top * n) / 4}
                </text>
              </g>
            ))}
            {daily.map((d, i) => {
              const total = Object.values(d.counts).reduce((a, b) => a + b, 0);
              const x = 52 + i * step;
              let height = 0;
              return (
                <Link
                  key={d.day}
                  to={`/cases?from=${d.day}&to=${d.day}`}
                  aria-label={`${fullDate(d.day)} 사건 ${total}건`}
                >
                  <title>
                    {`${fullDate(d.day)} · ${CATEGORIES.map((c) => `${c.name} ${d.counts[c.key]}건`).join(' · ')}`}
                  </title>
                  <rect x={x} y="24" width={step - 6} height="172" fill="transparent" />
                  {CATEGORIES.map((c, j) => {
                    const h = (d.counts[c.key] / top) * 160;
                    height += h;
                    return (
                      <rect
                        key={c.key}
                        x={x + step * 0.16}
                        y={192 - height}
                        width={step * 0.62}
                        height={h}
                        fill={categoryColors[j]}
                      />
                    );
                  })}
                  {total > 0 && (
                    <text
                      x={x + step * 0.47}
                      y={185 - (total / top) * 160}
                      textAnchor="middle"
                      fontSize="12"
                      fill="#28352e"
                    >
                      {total}
                    </text>
                  )}
                  {(days.length <= 14 || i % 3 === 0 || i === days.length - 1) && (
                    <text
                      x={x + step * 0.47}
                      y="218"
                      textAnchor="middle"
                      fill="#66716b"
                      fontSize="12"
                    >
                      {shortDate(d.day).slice(0, 5)}
                    </text>
                  )}
                </Link>
              );
            })}
          </svg>
        </div>
      </section>
      <section className="c2-chart-card" aria-labelledby="c2-types-title">
        <header>
          <div>
            <h2 id="c2-types-title">어떤 사건이 발생했나</h2>
            <p>선택 기간의 유형별 분포</p>
          </div>
        </header>
        <div className="c2-distribution">
          <svg
            viewBox="0 0 180 180"
            role="img"
            aria-label={CATEGORIES.map((c, i) => `${c.name} ${counts[i]}건`).join(', ')}
          >
            <circle cx="90" cy="90" r="67" fill="none" stroke="#edf0ee" strokeWidth="21" />
            {CATEGORIES.map((c, i) => {
              const share = views.length ? (counts[i] / views.length) * 100 : 0;
              const start = offset;
              offset += share;
              return share > 0 ? (
                <circle
                  key={c.key}
                  cx="90"
                  cy="90"
                  r="67"
                  pathLength="100"
                  fill="none"
                  stroke={categoryColors[i]}
                  strokeWidth="21"
                  strokeDasharray={`${share} ${100 - share}`}
                  strokeDashoffset={-start}
                  transform="rotate(-90 90 90)"
                />
              ) : null;
            })}
            <text x="90" y="88" textAnchor="middle" fontSize="32" fontWeight="600" fill="#202b25">
              {views.length}
            </text>
            <text x="90" y="112" textAnchor="middle" fontSize="13" fill="#68746c">
              수신 사건
            </text>
          </svg>
          <div>
            {CATEGORIES.map((c, i) => (
              <Link key={c.key} to={`/cases?period=${period}&category=${c.key}`}>
                <i style={{ background: categoryColors[i] }} />
                <span>{c.name}</span>
                <strong>
                  {counts[i]}
                  <small>건</small>
                </strong>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export function reportChartRows(value: Row) {
  const topic = rows(value.topics).find((t) => t.topic_id === 'namespace_usage');
  return rows(topic?.rows)
    .filter((r) => str(r.namespace))
    .map((r) => ({
      key: JSON.stringify([r.cluster_id, r.namespace, r.gpu_model]),
      cluster: str(r.cluster_id),
      namespace: str(r.namespace),
      model: str(r.gpu_model),
      activity: percent(r.activity_percent),
      memory: memoryPercent(obj(r.gpu_memory)),
      previous: r.comparison_status === 'comparable' ? percent(r.previous_activity_percent) : null,
    }));
}

function PercentBar({
  value,
  previous,
  label,
  color,
}: {
  value: number | null;
  previous?: number | null;
  label: string;
  color: string;
}) {
  return (
    <div className="c2-percent-bar">
      <svg
        viewBox="0 0 270 36"
        role="img"
        aria-label={`${label} ${value === null ? '미확인' : value.toFixed(2) + '%'}${previous != null ? ` · 이전 기간 ${previous.toFixed(2)}%` : ''}`}
      >
        <title>
          {`${label}${previous != null ? ` · 세로 점선: 이전 기간 ${previous.toFixed(2)}%` : ''}`}
        </title>
        <rect x="0" y="11" width="270" height="12" rx="3" fill="#edf0ee" />
        {[0, 50, 100].map((n) => (
          <line key={n} x1={n * 2.7} x2={n * 2.7} y1="8" y2="26" stroke="#dce2de" />
        ))}
        {value !== null && (
          <rect x="0" y="11" width={value * 2.7} height="12" rx="3" fill={color} />
        )}
        {value === 0 && <circle cx="2" cy="17" r="3" fill={color} />}
        {previous != null && (
          <line
            x1={previous * 2.7}
            x2={previous * 2.7}
            y1="5"
            y2="29"
            stroke="#44564b"
            strokeWidth="2"
            strokeDasharray="3 2"
          />
        )}
      </svg>
      <strong aria-hidden="true">{value === null ? '미확인' : value.toFixed(2) + '%'}</strong>
    </div>
  );
}

export function ReportVisualSummary({ value }: { value: Row }) {
  const topics = rows(value.topics);
  const usage = topics.find((t) => t.topic_id === 'namespace_usage');
  const incident = topics.find((t) => t.topic_id === 'incident_summary');
  const chartRows = reportChartRows(value);
  const observed = chartRows.filter((r) => r.activity !== null || r.memory !== null);
  const missing = chartRows.filter((r) => r.activity === null && r.memory === null);
  const summary = obj(incident?.summary);
  const current = count(summary.count),
    previous = count(summary.previous_count);
  const max = Math.max(current ?? 0, previous ?? 0, 1);
  const delta = current !== null && previous !== null ? current - previous : null;
  if (!usage && !incident) return null;
  return (
    <section id="c2-report-summary" className="c2-report-visual" aria-label="운영 지표 시각 요약">
      <div className="c2-report-visual-grid">
        {usage && (
          <section className="c2-chart-card">
            <header>
              <div>
                <h3>Namespace별 GPU 사용 관측</h3>
                <p>모델별 표시 · 활동률과 메모리 사용 비율은 서로 다른 지표입니다.</p>
              </div>
              <a href="#c2-namespace-charts">시간대별 추이 →</a>
            </header>
            <div className="c2-comparison-key">
              <span>
                <i style={{ background: '#76b900' }} />
                GPU 활동률
              </span>
              <span>
                <i style={{ background: '#397fc2' }} />
                GPU 메모리
              </span>
              <span>각 막대 0–100% · 세로 점선은 비교 가능한 이전 활동률</span>
            </div>
            <div className="c2-comparison-rows">
              {observed.map((r) => (
                <div className="c2-comparison-row" key={r.key}>
                  <div>
                    <strong>{r.namespace}</strong>
                    <small>
                      {r.cluster} · {r.model || '모델 미확인'}
                    </small>
                  </div>
                  <div>
                    <span>활동률</span>
                    <PercentBar
                      value={r.activity}
                      previous={r.previous}
                      label={`${r.cluster} ${r.namespace} ${r.model} 활동률`}
                      color="#76b900"
                    />
                  </div>
                  <div>
                    <span>메모리</span>
                    <PercentBar
                      value={r.memory}
                      label={`${r.cluster} ${r.namespace} ${r.model} 메모리 사용 비율`}
                      color="#397fc2"
                    />
                  </div>
                </div>
              ))}
              {!observed.length && (
                <p className="c2-chart-empty">
                  비교할 수 있는 활동률·메모리 관측이 없습니다. 자료 부족을 0%로 표시하지 않습니다.
                </p>
              )}
            </div>
            {!!missing.length && (
              <details className="c2-chart-missing">
                <summary>수치 미확인 {missing.length}개 Namespace·모델 기록 · 0%와 구분</summary>
                <ul>
                  {missing.map((r) => (
                    <li key={r.key}>
                      {r.cluster} / {r.namespace} · {r.model || '모델 미확인'}
                    </li>
                  ))}
                </ul>
                <a href="#namespace-summary-title">제외 사유와 관측 근거 확인 →</a>
              </details>
            )}
          </section>
        )}
        {incident && (
          <section className="c2-chart-card">
            <header>
              <div>
                <h3>기간 내 사건 비교</h3>
                <p>직전 같은 길이의 기간과 비교 · 수신 기록 기준</p>
              </div>
            </header>
            <div className="c2-period-comparison">
              <div className="c2-period-total">
                <strong>
                  {current === null ? '미확인' : current.toLocaleString()}
                  <small>{current === null ? '' : '건'}</small>
                </strong>
                <span>
                  {delta === null
                    ? '이전 기간 비교 미확인'
                    : `이전 기간 대비 ${delta > 0 ? '+' : ''}${delta}건`}
                </span>
              </div>
              <svg
                viewBox="0 0 360 104"
                role="img"
                aria-label={`현재 기간 ${current ?? '미확인'}건, 이전 기간 ${previous ?? '미확인'}건`}
              >
                {[
                  { label: '현재', n: current, color: '#76b900' },
                  { label: '이전', n: previous, color: '#b1bbb4' },
                ].map((v, i) => (
                  <g key={v.label}>
                    <text x="0" y={29 + i * 46} fill="#5f6f64" fontSize="13">
                      {v.label}
                    </text>
                    <rect x="44" y={12 + i * 46} width="250" height="24" rx="3" fill="#eff2f0" />
                    {v.n !== null && (
                      <rect
                        x="44"
                        y={12 + i * 46}
                        width={(v.n / max) * 250}
                        height="24"
                        rx="3"
                        fill={v.color}
                      />
                    )}
                    <text x="356" y={29 + i * 46} textAnchor="end" fill="#26372c" fontSize="14">
                      {v.n ?? '미확인'}
                    </text>
                  </g>
                ))}
              </svg>
              <a href="#incident-summary-title">장애 종류·노드별 내역 →</a>
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
