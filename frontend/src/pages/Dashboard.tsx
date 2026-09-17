import {
  Activity,
  ArrowUpRight,
  ChevronRight,
  CircleAlert,
  Cpu,
  Plus,
  Radio,
  RefreshCw,
  ScanSearch,
  Server,
  Sparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Badge, Empty, PageHead, Panel, TextLink } from '../components/ui';
import { assets, incidentId } from '../data/fixtures';
import { formatDate, inScope } from '../lib/domain';
import { useApp, useDatabase } from '../lib/store';
export function Dashboard() {
  const app = useApp();
  const { db } = useDatabase();
  const [metric, setMetric] = useState('활동');
  const [selected, setSelected] = useState<string[]>(['dgx-01', 'dgx-02', 'dgx-03', 'dgx-04']);
  const [refresh, setRefresh] = useState(false);
  const visible = assets.filter((a) => inScope(app.scope, a.cluster_id));
  useEffect(() => {
    setSelected((previous) => {
      const retained = previous.filter((name) => visible.some((a) => a.name === name));
      return retained.length ? retained : visible.slice(0, 4).map((a) => a.name);
    });
  }, [app.scope]);
  const incidents = db?.incidents.filter((i) => inScope(app.scope, i.cluster_id)) || [];
  const palette = [
    '#19755f',
    '#519ee0',
    '#ce9e4a',
    '#a895cb',
    '#718d82',
    '#d99585',
    '#507986',
    '#7981c6',
  ];
  const chart = Array.from({ length: 25 }, (_, i) => {
    const hours = app.period === '24h' ? 24 : app.period === '6h' ? 6 : 1;
    const minutes = 14 * 60 + 15 - hours * 60 + Math.round((i * hours * 60) / 24);
    return {
      time: `${String((Math.floor(minutes / 60) + 24) % 24).padStart(2, '0')}:${String((minutes + 1440) % 60).padStart(2, '0')}`,
      ...Object.fromEntries(
        visible.map((a, n) => [
          a.name,
          a.utilization === null
            ? null
            : Math.max(
                0,
                Math.min(
                  metric === '전력' ? 550 : 100,
                  (metric === '활동' ? a.utilization : metric === 'VRAM' ? a.memory! : a.power!) +
                    (Math.sin(i * 0.8 + n) * 7 + Math.cos(i * 0.37 + n) * 4) *
                      (metric === '전력' ? 4 : 1),
                ),
              ),
        ]),
      ),
    };
  });
  return (
    <div className="page dashboard-page">
      <PageHead
        eyebrow="OPERATIONS OVERVIEW"
        title="운영 대시보드"
        description="GPU 인프라의 현재 상태와 먼저 살펴볼 신호를 확인하세요."
        actions={
          <>
            <span className="snapshot-label">
              <span className="green-dot" />
              관측 기준 14:15 KST
            </span>
            <button
              className={`button refresh ${refresh ? 'refreshing' : ''}`}
              onClick={() => {
                setRefresh(true);
                setTimeout(() => {
                  setRefresh(false);
                  app.notify(
                    '데모 스냅샷을 다시 조회했습니다. 기준 시각은 2026.09.16 14:15입니다.',
                  );
                }, 500);
              }}
            >
              <RefreshCw size={15} />
              새로고침
            </button>
          </>
        }
      />
      <div className="metrics-grid">
        <Link to="/cases" className="metric-card">
          <div className="metric-label">
            열린 사건
            <span className="metric-icon amber">
              <CircleAlert size={18} />
            </span>
          </div>
          <div className="metric-value">
            {incidents.filter((i) => i.status !== 'closed' && i.status !== 'resolved').length}
            <span>건</span>
            <span className="mini-badge amber">검토 필요</span>
          </div>
          <div className="metric-footer">
            운영자 확인이 필요한 사건
            <ArrowUpRight size={16} />
          </div>
        </Link>
        <Link to="/fleet/assets" className="metric-card">
          <div className="metric-label">
            관측 대상 GPU
            <span className="metric-icon green">
              <Cpu size={18} />
            </span>
          </div>
          <div className="metric-value">
            {visible.length * 8}
            <span>개</span>
            <span className="metric-sub">/ {visible.length} Nodes</span>
          </div>
          <div className="metric-footer">
            <span>
              <i className="green-dot" />
              {visible.length - Number(visible.some((a) => a.status === 'delayed'))}개 노드 정상
              수신
            </span>
            <ArrowUpRight size={16} />
          </div>
        </Link>
        <Link to="/fleet/quality" className="metric-card">
          <div className="metric-label">
            관측 지연
            <span className="metric-icon blue">
              <Radio size={18} />
            </span>
          </div>
          <div className="metric-value">
            {visible.filter((a) => a.status === 'delayed').length}
            <span>노드</span>
          </div>
          <div className="metric-footer">
            원본 수신 시각 확인
            <ArrowUpRight size={16} />
          </div>
        </Link>
        <Link to="/fleet/quality" className="metric-card">
          <div className="metric-label">
            분석 준비 상태
            <span className="metric-icon purple">
              <ScanSearch size={18} />
            </span>
          </div>
          <div className="metric-value text-value">일부 근거 부족</div>
          <div className="metric-footer">
            <span className="amber-text">할당 이력·공동 관측률 확인</span>
            <ArrowUpRight size={16} />
          </div>
        </Link>
      </div>
      <div className="section-title">
        <h2>
          우선 검토 항목{' '}
          <span className="counter">
            {Number(inScope(app.scope, 'cpc-1')) + Number(inScope(app.scope, 'cpc-2'))}
          </span>
        </h2>
        <span>관측된 신호를 근거와 함께 확인하세요.</span>
      </div>
      <div className="attention-grid">
        {inScope(app.scope, 'cpc-1') && (
          <Link to={`/incidents/${incidentId}`} className="attention-card">
            <span className="attention-icon">
              <CircleAlert size={21} />
            </span>
            <div>
              <div className="attention-title">
                <h3>
                  dgx-03 <span>GPU 응답 중단</span>
                </h3>
                <Badge status="partial" />
              </div>
              <p>Xid 79 오류가 관측되었습니다. 원인 후보와 작업 영향을 검토하세요.</p>
              <span className="attention-meta">
                CPC-1<span>·</span>13:42 발생<span>·</span>INC-2026-042
              </span>
            </div>
            <ChevronRight size={19} />
          </Link>
        )}
        {inScope(app.scope, 'cpc-2') && (
          <Link to="/fleet/quality" className="attention-card neutral">
            <span className="attention-icon">
              <Radio size={21} />
            </span>
            <div>
              <div className="attention-title">
                <h3>
                  dgx-08 <span>관측 수신 지연</span>
                </h3>
                <Badge status="delayed" />
              </div>
              <p>마지막 수신 이후 12분이 지났습니다. 현재 장비 상태는 미확인입니다.</p>
              <span className="attention-meta">
                CPC-2<span>·</span>마지막 수신 14:03<span>·</span>수집 경로 확인
              </span>
            </div>
            <ChevronRight size={19} />
          </Link>
        )}
      </div>
      <div className="observation-grid">
        <Panel
          title="GPU 자원 추이"
          description="선택 노드의 물리 GPU 평균 · 데모 관측 추이"
          action={
            <div className="segmented">
              {['활동', 'VRAM', '전력'].map((m) => (
                <button
                  key={m}
                  className={m === metric ? 'active' : ''}
                  onClick={() => setMetric(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          }
        >
          <div className="chart-meta">
            <span>{metric === '전력' ? '평균 전력 (W)' : '평균 ' + metric + ' (%)'}</span>
            <button
              className="text-button"
              onClick={() =>
                app.ask(
                  `${selected.filter((n) => visible.some((a) => a.name === n)).join(', ')} · ${metric} 추이 · ${app.period} · 2026.09.16 14:15 KST`,
                )
              }
            >
              <Sparkles size={14} />이 그래프에 질문
            </button>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chart} margin={{ top: 10, right: 15, left: -23, bottom: 0 }}>
                <defs>
                  {palette.map((color, i) => (
                    <linearGradient id={`fill${i}`} key={i} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={color} stopOpacity={0.08} />
                      <stop offset="100%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid vertical={false} stroke="#e9eeed" strokeDasharray="3 4" />
                <XAxis
                  dataKey="time"
                  tickLine={false}
                  axisLine={false}
                  minTickGap={40}
                  tick={{ fontSize: 11, fill: '#7d8985' }}
                  dy={7}
                />
                <YAxis
                  domain={[0, metric === '전력' ? 600 : 100]}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 11, fill: '#7d8985' }}
                />
                <Tooltip
                  contentStyle={{ border: '1px solid #dfe7e3', borderRadius: 8, fontSize: 12 }}
                  formatter={(v) => [
                    `${Number(v).toFixed(1)} ${metric === '전력' ? 'W' : '%'}`,
                    undefined,
                  ]}
                />
                {visible
                  .filter((a) => selected.includes(a.name))
                  .map((a) => {
                    const i = assets.indexOf(a);
                    return (
                      <Area
                        key={a.id}
                        type="monotone"
                        dataKey={a.name}
                        stroke={palette[i]}
                        fill={`url(#fill${i})`}
                        strokeWidth={2}
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    );
                  })}
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-legend">
            {visible.map((a) => (
              <button
                className={!selected.includes(a.name) ? 'inactive' : ''}
                key={a.id}
                onClick={() =>
                  setSelected((s) =>
                    s.includes(a.name) ? s.filter((n) => n !== a.name) : [...s, a.name],
                  )
                }
              >
                <span style={{ background: palette[assets.indexOf(a)] }} />
                {a.name}
                {a.status === 'delayed' && ' · 누락'}
              </button>
            ))}
          </div>
          <div className="chart-footnote">
            <InfoIcon />
            VRAM 점유는 연산 활동과 다릅니다. 누락된 관측값은 0으로 표시하지 않습니다.
          </div>
        </Panel>
        <Panel
          title="클러스터 현황"
          description="CPC별 인프라 관측"
          action={
            <Link className="icon-link" aria-label="자산 전체 보기" to="/fleet/assets">
              <ArrowUpRight size={17} />
            </Link>
          }
        >
          {['cpc-1', 'cpc-2']
            .filter((c) => inScope(app.scope, c))
            .map((c) => (
              <Link key={c} to={`/fleet/assets?cluster=${c}`} className="cluster-card">
                <div className="cluster-heading">
                  <span className="cluster-icon">
                    <Server size={18} />
                  </span>
                  <div>
                    <h3>{c.toUpperCase()}</h3>
                    <small>{c === 'cpc-1' ? 'H100' : 'A100'} GPU Cluster</small>
                  </div>
                  <Badge
                    status={c === 'cpc-1' ? 'healthy' : 'delayed'}
                    label={c === 'cpc-1' ? '수신 정상' : '일부 지연'}
                  />
                </div>
                <div className="cluster-stats">
                  <span>
                    <b>4</b> Nodes
                  </span>
                  <span>
                    <b>32</b> GPUs
                  </span>
                  <span>
                    <b>{c === 'cpc-1' ? '4' : '3'}/4</b> 수신
                  </span>
                </div>
                <div className="node-blocks">
                  {assets
                    .filter((a) => a.cluster_id === c)
                    .map((a) => (
                      <div title={`${a.name}: ${a.status}`} key={a.id} className={a.status}>
                        {Array.from({ length: 8 }, (_, i) => (
                          <i key={i} />
                        ))}
                      </div>
                    ))}
                </div>
                <div className="cluster-foot">
                  <span>
                    <i className="green-dot" />
                    정상 수신
                  </span>
                  <span>
                    <i className="amber-dot" />
                    주의 / 지연
                  </span>
                </div>
              </Link>
            ))}
          <Link to="/fleet/quality" className="cluster-bottom">
            관측 품질 자세히 보기
            <ChevronRight size={15} />
          </Link>
        </Panel>
      </div>
      <Panel
        title="최근 사건"
        description="사건의 운영 상태와 분석의 산출 상태를 따로 확인합니다."
        action={<TextLink to="/cases">전체 사건 보기</TextLink>}
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>사건 / 관측 신호</th>
                <th>대상</th>
                <th>발생 시각 (KST)</th>
                <th>사건 상태</th>
                <th>산출 상태</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.id}>
                  <td>
                    <Link className="incident-title" to={`/incidents/${i.id}`}>
                      <span className={`severity-mark ${i.severity}`} />
                      <div>
                        <b>{i.title}</b>
                        <small>{i.label}</small>
                      </div>
                    </Link>
                  </td>
                  <td>
                    <b className="mono">{i.node}</b>
                    <small>{i.cluster_id.toUpperCase()}</small>
                  </td>
                  <td>{formatDate(i.created_at)}</td>
                  <td>
                    <Badge status={i.status} />
                  </td>
                  <td>
                    <Badge status={i.analysis_id ? 'partial' : null} />
                  </td>
                  <td>
                    <Link
                      className="icon-link"
                      aria-label={`${i.label} 상세`}
                      to={`/incidents/${i.id}`}
                    >
                      <ChevronRight size={18} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!incidents.length && <Empty />}
        </div>
      </Panel>
      <div className="dashboard-bottom">
        <div>
          <Sparkles size={18} />
          <span>데이터에서 다음 행동을 찾으세요.</span>
          <small>근거를 바탕으로 조사하고, 운영 현황을 보고서로 정리합니다.</small>
        </div>
        <Link to="/analyses/new">
          <Plus size={15} />새 RCA 조사
        </Link>
        <Link to="/reports">
          운영 보고서 만들기
          <ArrowUpRight size={15} />
        </Link>
      </div>
    </div>
  );
}
function InfoIcon() {
  return <Activity size={13} />;
}
