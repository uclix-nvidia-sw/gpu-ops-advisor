import { useState } from 'react';
import { ReportScope } from './ReportMeta';
import { reportTitle } from '../lib/workflow';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  num,
  obj,
  queryPath,
  rows,
  str,
  strings,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { reportPeriodLabel } from '../lib/reportPeriod';
import { useApp } from '../lib/store';
import { QueryState } from './live';
import { Badge } from './ui';

export interface NamespaceUsage {
  key: string;
  label: string;
  cluster: string;
  model: string;
  activity: number | null;
  previous: number | null;
  gpus: number | null;
  pending: number | null;
  hourly: Record<string, number | null>;
}

const value = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const hourText = (iso: string) =>
  new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    hour12: false,
  }).format(new Date(iso));

/** Namespace rows of a stored Ops report; model-level rows without a Namespace are skipped. */
export function opsUsage(result: Row, comparableOnly = false) {
  const topics = rows(result.topics);
  const usage = topics.find((t) => t.topic_id === 'namespace_usage');
  const incidents = obj(topics.find((t) => t.topic_id === 'incident_summary')?.summary);
  const pending = new Map(
    rows(usage?.workloads).map((w) => {
      const peaks = rows(w.hours)
        .map((h) => value(h.pending_peak))
        .filter((v): v is number => v !== null);
      return [`${str(w.cluster_id)}/${str(w.namespace)}`, peaks.length ? Math.max(...peaks) : null];
    }),
  );
  const items: NamespaceUsage[] = rows(usage?.rows)
    .filter((r) => str(r.namespace))
    .map((r) => ({
      key: `${str(r.cluster_id)}/${str(r.namespace)}/${str(r.gpu_model)}`,
      label: str(r.namespace),
      cluster: str(r.cluster_id),
      model: str(r.gpu_model),
      activity: value(r.activity_percent),
      previous:
        !comparableOnly || r.comparison_status === 'comparable'
          ? value(r.previous_activity_percent)
          : null,
      gpus: value(r.observed_gpu_count),
      pending: pending.get(`${str(r.cluster_id)}/${str(r.namespace)}`) ?? null,
      hourly: Object.fromEntries(
        rows(r.hours).map((h) => [str(h.start), value(h.activity_percent)]),
      ),
    }));
  // Same Namespace on another cluster or GPU model gets its origin in the label.
  const names = items.map((u) => u.label);
  items.forEach((u) => {
    if (names.filter((n) => n === u.label).length > 1)
      u.label = `${u.label} (${u.cluster} · ${u.model})`;
  });
  const hours = [...new Set(items.flatMap((u) => Object.keys(u.hourly)))].sort();
  return {
    items,
    hours,
    alerts:
      typeof incidents.count === 'number'
        ? { count: num(incidents.count), previous: value(incidents.previous_count) }
        : null,
  };
}

// Cove categorical order; colour follows the Namespace, not its rank.
const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6'];
const OTHER = '#b4b2a9';
const pct = (v: unknown) => (typeof v === 'number' ? `${Math.round(v)}%` : '관측 부족');

/** Dashboard section: GPU use per Namespace from the latest stored Ops report. */
export function snapshotReports(items: Row[]) {
  return items
    .filter(
      (r) =>
        r.status === 'succeeded' &&
        r.result_ref &&
        !r.deletion &&
        strings(r.topic_ids).includes('namespace_usage'),
    )
    .sort(
      (a, b) =>
        (Date.parse(str(obj(b.time_range).end)) || 0) -
        (Date.parse(str(obj(a.time_range).end)) || 0),
    );
}
export function OpsUsage({ snapshot = false }: { snapshot?: boolean }) {
  const [selected, setSelected] = useState('');
  const [chartsOpen, setChartsOpen] = useState(true);
  const app = useApp();
  const list = useList(
    app.ready ? queryPath('/reports', { scope: app.scope, status: 'succeeded', limit: 20 }) : null,
  );
  const snapshots = snapshotReports(list.items);
  const latest = snapshot
    ? snapshots.find((r) => r.id === selected) || snapshots[0]
    : list.items.find((r) => strings(r.topic_ids).includes('namespace_usage'));
  const id = str(latest?.id);
  const report = useResource(id ? `/reports/${encodeURIComponent(id)}` : null);
  const range = obj(latest?.time_range);
  const available =
    !snapshot ||
    (report.data?.status === 'succeeded' && report.data?.result_ref && !report.data?.deletion);
  const { items, hours, alerts } = opsUsage(available ? obj(report.data?.result) : {}, snapshot);
  const color = new Map(items.map((u, i) => [u.key, SERIES[i % SERIES.length]]));
  const measured = items.filter((u) => u.activity !== null);
  const missing = items.filter((u) => u.activity === null);
  const byActivity = [...measured].sort((a, b) => b.activity! - a.activity!);
  const lines = byActivity.slice(0, 3);
  const hourly = hours.map((h) => ({
    hour: hourText(h),
    ...Object.fromEntries(lines.map((u) => [u.key, u.hourly[h] ?? null])),
  }));
  const byGpus = items.filter((u) => u.gpus).sort((a, b) => b.gpus! - a.gpus!);
  const gpuTotal = byGpus.reduce((a, u) => a + u.gpus!, 0);
  const slices = byGpus
    .slice(0, 3)
    .map((u) => ({ name: u.label, value: u.gpus!, fill: color.get(u.key)! }));
  const rest = byGpus.slice(3).reduce((a, u) => a + u.gpus!, 0);
  if (rest) slices.push({ name: `기타 ${byGpus.length - 3}개`, value: rest, fill: OTHER });
  const waiting = items.filter((u) => u.pending).sort((a, b) => b.pending! - a.pending!);
  const top = byActivity[0];
  const label = (key: string) => items.find((u) => u.key === key)?.label || key;
  return (
    <section className="oh-card ops-usage" aria-labelledby="ops-usage-title">
      <div className="oh-card-h">
        <div>
          <h2 id="ops-usage-title">
            {snapshot ? '저장된 운영 보고서 요약' : 'GPU 사용 현황 · Ops 보고서'}
          </h2>
          <p>
            {latest
              ? `${reportPeriodLabel(str(range.start), str(range.end))} 분석 · 저장된 보고서 기준`
              : 'Namespace 사용 현황이 담긴 최근 Ops 보고서 기준'}
          </p>
        </div>
        {latest && (
          <span className="ops-usage-head">
            <Badge status={str(latest.result_status) || null} />
            <Link className="oh-btn line" to={`/reports/${encodeURIComponent(id)}`}>
              보고서 열기 →
            </Link>
          </span>
        )}
      </div>
      <div className="oh-card-b">
        {snapshot && (
          <div className="c2-snapshot-meta">
            <p>
              사건 조회 기간과 별개인 저장 결과입니다. 아래에 표시된 분석 기간을 기준으로 읽으세요.
            </p>
            {latest && <ReportScope job={latest} compact />}
            <details>
              <summary>다른 보고서 선택</summary>
              <p>불러온 보고서 중 분석 종료일 최신순입니다.</p>
              {snapshots.length > 0 && (
                <label>
                  요약할 보고서
                  <select value={id} onChange={(e) => setSelected(e.target.value)}>
                    {snapshots.map((r) => (
                      <option key={str(r.id)} value={str(r.id)}>
                        {reportTitle(r)} ·{' '}
                        {reportPeriodLabel(
                          str(obj(r.time_range).start),
                          str(obj(r.time_range).end),
                        )}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {list.hasNextPage && (
                <button
                  className="button"
                  disabled={list.isFetchingNextPage}
                  onClick={() => void list.fetchNextPage()}
                >
                  이전 보고서 더 불러오기
                </button>
              )}
            </details>
          </div>
        )}
        <QueryState
          query={list}
          empty={!latest}
          emptyTitle="Namespace 사용 현황이 담긴 Ops 보고서가 없습니다."
          emptyDescription="Ops 보고서에서 Namespace 사용 주제를 포함해 보고서를 만들면 여기에 표시됩니다."
          emptyAction={
            <Link className="button" to="/reports/new">
              보고서 만들기
            </Link>
          }
        >
          <QueryState
            query={report}
            empty={!items.length}
            emptyTitle="이 보고서에 Namespace 사용 행이 없습니다."
            emptyDescription="보고서 본문에서 관측 한계와 누락 자료를 확인하세요."
          >
            <div className="oh-kpis ops-usage-kpis">
              <div className="oh-kpi">
                <span>연결 GPU</span>
                <strong>
                  {byGpus.length
                    ? `${gpuTotal}대`
                    : items.some((u) => u.gpus === 0)
                      ? '0대'
                      : '관측 부족'}
                </strong>
                <small>{byGpus.length}개 Namespace · 기간 중 고유 대수</small>
              </div>
              <div className="oh-kpi">
                <span>평균 활동률 최고</span>
                <strong>{pct(top?.activity)}</strong>
                <small>{top?.label || '관측 부족'}</small>
              </div>
              <div className="oh-kpi">
                <span>대기 Pod 최대</span>
                <strong>
                  {items.some((u) => u.pending !== null)
                    ? `${waiting[0]?.pending ?? 0}개`
                    : '관측 부족'}
                </strong>
                <small>
                  {waiting[0]?.label ||
                    (items.some((u) => u.pending !== null)
                      ? '관측된 대기 Pod 없음'
                      : '대기 Pod 자료 미확인')}
                </small>
              </div>
              <div className="oh-kpi">
                <span>기간 내 알림</span>
                <strong>{alerts ? `${alerts.count}건` : '미확인'}</strong>
                <small>
                  {alerts?.previous != null ? `비교 기간 ${alerts.previous}건` : '비교 기간 미확인'}
                </small>
              </div>
            </div>
            {snapshot && (
              <button
                className="button c2-chart-toggle"
                aria-expanded={chartsOpen}
                aria-controls="c2-usage-charts"
                onClick={() => setChartsOpen(!chartsOpen)}
              >
                {chartsOpen ? '그래프 접기' : '활동률·연결 GPU·작업 대기 그래프 보기'}
              </button>
            )}
            <div
              className="ops-usage-grid"
              id={snapshot ? 'c2-usage-charts' : undefined}
              hidden={snapshot && !chartsOpen}
            >
              {(!snapshot || chartsOpen) && (
                <>
                  <figure>
                    <figcaption>
                      <b>Namespace별 GPU 활동률</b>
                      <small>분석 기간 평균과 비교 기간 평균</small>
                    </figcaption>
                    <ResponsiveContainer
                      width="100%"
                      height={Math.max(160, byActivity.length * 34 + 60)}
                    >
                      <BarChart data={byActivity} layout="vertical" margin={{ left: 8, right: 16 }}>
                        <CartesianGrid horizontal={false} stroke="#e1e0d9" />
                        <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                        <YAxis
                          type="category"
                          dataKey="label"
                          width={200}
                          tick={{ fontSize: 11 }}
                        />
                        <Tooltip formatter={(v) => pct(v)} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Bar
                          dataKey="activity"
                          name="분석 기간"
                          fill="#2a78d6"
                          radius={[0, 4, 4, 0]}
                          barSize={9}
                        />
                        <Bar
                          dataKey="previous"
                          name="비교 기간"
                          fill={OTHER}
                          radius={[0, 4, 4, 0]}
                          barSize={9}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                    {missing.length > 0 && (
                      <small className="muted">
                        관측 부족(0%가 아님): {missing.map((u) => u.label).join(', ')}
                      </small>
                    )}
                  </figure>
                  <figure>
                    <figcaption>
                      <b>시간대별 활동률</b>
                      <small>1시간 평균 · 활동률 상위 {lines.length}개 Namespace · KST</small>
                    </figcaption>
                    <ResponsiveContainer width="100%" height={240}>
                      <LineChart data={hourly} margin={{ left: 0, right: 16 }}>
                        <CartesianGrid vertical={false} stroke="#e1e0d9" />
                        <XAxis dataKey="hour" tick={{ fontSize: 11 }} interval={2} />
                        <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} width={44} />
                        <Tooltip formatter={(v, key) => [pct(v), label(String(key))]} />
                        <Legend
                          formatter={(key) => label(String(key))}
                          wrapperStyle={{ fontSize: 12 }}
                        />
                        {lines.map((u, i) => (
                          <Line
                            key={u.key}
                            dataKey={u.key}
                            stroke={color.get(u.key)}
                            strokeWidth={2}
                            strokeDasharray={['', '5 3', '2 2'][i]}
                            dot={false}
                            connectNulls={false}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </figure>
                  <figure>
                    <figcaption>
                      <b>GPU 연결 분포</b>
                      <small>Namespace별 연결 GPU · 동시 사용 대수 아님</small>
                    </figcaption>
                    {snapshot ? (
                      <div className="aggregate-table-scroll">
                        <table className="c2-gpu-observed-table">
                          <caption className="sr-only">기간 중 Namespace·모델별 관측 GPU</caption>
                          <thead>
                            <tr>
                              <th>Namespace / 모델</th>
                              <th>관측 GPU</th>
                            </tr>
                          </thead>
                          <tbody>
                            {byGpus.map((u) => (
                              <tr key={u.key}>
                                <th>
                                  {u.label}
                                  <small>
                                    {u.cluster} · {u.model}
                                  </small>
                                </th>
                                <td>{u.gpus}대</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={250}>
                        <PieChart>
                          <Pie
                            data={slices}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={48}
                            outerRadius={78}
                            stroke="#fff"
                            strokeWidth={2}
                          >
                            {slices.map((s) => (
                              <Cell key={s.name} fill={s.fill} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(v) => `${v}대`} />
                          <Legend
                            formatter={(name, entry) => `${name} ${obj(entry.payload).value}대`}
                            wrapperStyle={{ fontSize: 12 }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    )}
                  </figure>
                  <figure>
                    <figcaption>
                      <b>대기 Pod 최대</b>
                      <small>
                        {snapshot
                          ? '관측한 시간대의 최대값 · 대기 원인은 별도 확인'
                          : '활동률이 높은데 대기 Pod도 있으면 자원 부족을 확인하세요'}
                      </small>
                    </figcaption>
                    {waiting.length ? (
                      <ResponsiveContainer
                        width="100%"
                        height={Math.max(120, waiting.length * 34 + 40)}
                      >
                        <BarChart data={waiting} layout="vertical" margin={{ left: 8, right: 16 }}>
                          <CartesianGrid horizontal={false} stroke="#e1e0d9" />
                          <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                          <YAxis
                            type="category"
                            dataKey="label"
                            width={200}
                            tick={{ fontSize: 11 }}
                          />
                          <Tooltip formatter={(v) => `${v}개`} />
                          <Bar
                            dataKey="pending"
                            name="대기 Pod"
                            fill="#eda100"
                            radius={[0, 4, 4, 0]}
                            barSize={12}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="muted">
                        {snapshot && !items.some((u) => u.pending !== null)
                          ? '대기 관측 자료가 없습니다.'
                          : snapshot
                            ? '관측된 시간대에 대기 Pod가 없었습니다.'
                            : '분석 기간에 대기 Pod가 관측되지 않았습니다.'}
                      </p>
                    )}
                  </figure>
                </>
              )}
            </div>
            <p className="muted ops-usage-note">
              활동률은 Namespace에 연결된 GPU의 관측 표본 평균이며 실제 소비량·할당 효율이 아닙니다.
            </p>
          </QueryState>
        </QueryState>
      </div>
    </section>
  );
}
