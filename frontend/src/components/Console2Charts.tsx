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
        <div
          className="c2-category-bars"
          role="group"
          aria-label={CATEGORIES.map((c, i) => `${c.name} ${counts[i]}건`).join(', ')}
        >
          {CATEGORIES.map((c, i) => ({ ...c, count: counts[i], color: categoryColors[i] }))
            .sort((a, b) => b.count - a.count)
            .map((c) => (
              <Link key={c.key} to={`/cases?period=${period}&category=${c.key}`}>
                <span>{c.name}</span>
                <strong>{c.count}건</strong>
                <span className="c2-count-track" aria-hidden="true">
                  <i
                    style={{
                      width: `${(c.count / Math.max(1, ...counts)) * 100}%`,
                      background: c.color,
                    }}
                  />
                </span>
              </Link>
            ))}
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
              <p className="c2-chart-note">
                현재 기간 {current ?? '미확인'}건, 이전 기간 {previous ?? '미확인'}건
              </p>
              <a href="#incident-summary-title">장애 종류·노드별 내역 →</a>
            </div>
          </section>
        )}
      </div>
    </section>
  );
}

export function IncidentBreakdown({ summary }: { summary: Row }) {
  const changes = rows(summary.categories)
    .flatMap((r) => {
      const now = count(r.count),
        before = count(r.previous_count);
      return now === null || before === null
        ? []
        : [{ cluster_id: str(r.cluster_id), name: str(r.name), delta: now - before, now, before }];
    })
    .filter((r) => r.delta !== 0)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const maxChange = Math.max(1, ...changes.map((r) => Math.abs(r.delta)));
  const nodes = new Map<string, { name: string; count: number }>();
  const seen = new Set<string>();
  for (const r of rows(summary.incidents)) {
    const id = str(r.id);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const name = `${str(r.cluster_id) || '클러스터 미확인'} / ${str(obj(r.target).node) || '노드 미확인'}`;
    const previous = nodes.get(name);
    nodes.set(name, { name, count: (previous?.count || 0) + 1 });
  }
  const ranked = [...nodes.values()].sort((a, b) => b.count - a.count);
  const maxNode = Math.max(1, ...ranked.map((n) => n.count));
  return (
    <div id="c2-incident-evidence" className="c2-incident-evidence">
      <section className="c2-chart-card">
        <h3>어떤 오류 종류가 늘거나 줄었나</h3>
        <p className="c2-chart-note">
          직전 같은 길이의 기간 대비 · 변화 폭 상위 6개 · 수신 기록 기준
        </p>
        <div className="c2-category-bars">
          {changes.slice(0, 6).map((r) => (
            <div key={`${r.cluster_id}/${r.name}`}>
              <span>
                {str(r.name)}{' '}
                <small>
                  {str(r.cluster_id)} · {r.before} → {r.now}건
                </small>
              </span>
              <strong>
                {r.delta > 0 ? '+' : ''}
                {r.delta}건
              </strong>
              <span className="c2-count-track" aria-hidden="true">
                <i
                  style={{
                    width: `${(Math.abs(r.delta) / maxChange) * 100}%`,
                    background: r.delta > 0 ? '#397fc2' : '#72837a',
                  }}
                />
              </span>
            </div>
          ))}
        </div>
        {!changes.length && (
          <p>
            비교 가능한 증감이 없습니다. 전체 종류별 표에서 동일 값과 비교 자료 유무를 확인하세요.
          </p>
        )}
      </section>
      <section className="c2-chart-card">
        <h3>어느 노드의 기록을 확인할까</h3>
        <p className="c2-chart-note">
          저장된 사건 내역 {seen.size}건 · 상위 6개 · 현재 장애 수가 아닙니다.
        </p>
        <div className="c2-category-bars">
          {ranked.slice(0, 6).map((n) => (
            <div key={n.name}>
              <span>{n.name}</span>
              <strong>{n.count}건</strong>
              <span className="c2-count-track" aria-hidden="true">
                <i style={{ width: `${(n.count / maxNode) * 100}%`, background: '#76a900' }} />
              </span>
            </div>
          ))}
        </div>
        {!ranked.length && <p>노드별로 대조할 사건 내역이 없습니다.</p>}
        <p className="c2-chart-note">
          시험 알림 여부와 관련 RCA를 대조하세요. 수신 건수만으로 위험도·동일 원인을 판정하지
          않습니다.
        </p>
      </section>
    </div>
  );
}
