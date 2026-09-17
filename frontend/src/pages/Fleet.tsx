import { ArrowUpRight, ChevronRight, Cpu, Radio, ScanSearch, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Badge,
  Empty,
  Modal,
  NavTabs,
  Notice,
  PageHead,
  Panel,
  SearchBox,
  TextLink,
} from '../components/ui';
import { assets, pods } from '../data/fixtures';
import { inScope } from '../lib/domain';
import { useApp } from '../lib/store';
const tabs = [
  { to: '/fleet/assets', label: '장비·GPU' },
  { to: '/fleet/workloads', label: '작업 연결' },
  { to: '/fleet/quality', label: '관측 상태' },
];
export function Fleet({ view }: { view: 'assets' | 'workloads' | 'quality' }) {
  const app = useApp();
  const [params] = useSearchParams();
  const [search, setSearch] = useState('');
  const [cluster, setCluster] = useState(params.get('cluster') || 'all');
  const [selected, setSelected] = useState<string | null>(null);
  const [gpu, setGpu] = useState(0);
  const [at, setAt] = useState('current');
  const [historical, setHistorical] = useState('2026-09-16T13:42');
  const visible = assets.filter(
    (a) =>
      inScope(app.scope, a.cluster_id) &&
      (cluster === 'all' || a.cluster_id === cluster) &&
      `${a.name} ${a.model}`.toLowerCase().includes(search.toLowerCase()),
  );
  const node = assets.find((a) => a.id === selected);
  const podRows = pods.filter(
    (p) =>
      inScope(app.scope, p.cluster_id, p.namespace) &&
      (cluster === 'all' || p.cluster_id === cluster) &&
      `${p.name} ${p.id}`.includes(search),
  );
  return (
    <div className="page">
      <PageHead
        eyebrow="FLEET & OBSERVABILITY"
        title="자산·관측"
        description="장비에서 작업까지, 연결 관계와 관측의 품질을 함께 살펴보세요."
        actions={
          <button className="button" onClick={() => app.ask('자산과 GPU 연결 관계')}>
            <Sparkles size={16} />
            선택 범위에 질문
          </button>
        }
      />
      <NavTabs items={tabs} />
      {view === 'assets' && (
        <>
          <div className="toolbar">
            <SearchBox
              value={search}
              onChange={setSearch}
              placeholder="Node 이름 또는 GPU 모델 검색"
            />
            <select
              aria-label="CPC 필터"
              value={cluster}
              onChange={(e) => setCluster(e.target.value)}
            >
              <option value="all">전체 CPC</option>
              {app.scope.clusters.map((c) => (
                <option key={c.cluster_id} value={c.cluster_id}>
                  {c.cluster_id.toUpperCase()}
                </option>
              ))}
            </select>
            <span className="toolbar-count">
              {visible.length} Nodes · {visible.length * 8} GPUs
            </span>
          </div>
          <Panel>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Node / CPC</th>
                    <th>GPU 모델</th>
                    <th>GPU</th>
                    <th>활동</th>
                    <th>VRAM 점유</th>
                    <th>평균 전력</th>
                    <th>관측 상태</th>
                    <th>마지막 수신</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <button
                          className="asset-name"
                          onClick={() => {
                            setSelected(a.id);
                            setGpu(0);
                          }}
                        >
                          <span className="table-icon">
                            <Cpu size={18} />
                          </span>
                          <span>
                            <b>{a.name}</b>
                            <small>{a.cluster_id.toUpperCase()}</small>
                          </span>
                        </button>
                      </td>
                      <td>{a.model}</td>
                      <td>8</td>
                      <td>
                        <Meter value={a.utilization} />
                      </td>
                      <td>
                        <Meter value={a.memory} pale />
                      </td>
                      <td>{a.power === null ? '—' : `${a.power} W`}</td>
                      <td>
                        <Badge status={a.status} />
                      </td>
                      <td className="mono">{a.last_seen}</td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`${a.name} 상세`}
                          onClick={() => {
                            setSelected(a.id);
                            setGpu(0);
                          }}
                        >
                          <ChevronRight size={17} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && <Empty />}
            </div>
            <div className="table-footer">
              2026.09.16 고정 스냅샷 · 물리 GPU 단위
              <span>누락값 — : 수신 지연으로 현재 상태 미확인</span>
            </div>
          </Panel>
        </>
      )}
      {view === 'workloads' && (
        <>
          <Notice>
            노드 배치·GPU 관계·활동은 독립된 상태입니다. Pending은 노드 미배치를 의미하지 않습니다.
          </Notice>
          <div className="toolbar">
            <SearchBox value={search} onChange={setSearch} placeholder="Pod 이름 또는 UID 검색" />
            <div className="segmented">
              <button className={at === 'current' ? 'active' : ''} onClick={() => setAt('current')}>
                현재 스냅샷
              </button>
              <button className={at === 'past' ? 'active' : ''} onClick={() => setAt('past')}>
                과거 시각
              </button>
            </div>
            {at === 'past' && (
              <input
                aria-label="관계 기준 시각"
                type="datetime-local"
                value={historical}
                onChange={(e) => setHistorical(e.target.value)}
              />
            )}
          </div>
          {at === 'past' ? (
            <Panel>
              <Empty
                title="선택 시각의 관계 근거가 없습니다."
                description={`${historical.replace('T', ' ')} KST의 관계 이력이 데모 데이터에 없습니다. 현재 매핑으로 과거 관계를 대체하지 않습니다.`}
              />
            </Panel>
          ) : (
            <Panel>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Pod / UID</th>
                      <th>CPC / Namespace</th>
                      <th>Kubernetes phase</th>
                      <th>노드 배치</th>
                      <th>GPU 연결</th>
                      <th>활동</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {podRows.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <b>{p.name}</b>
                          <small className="mono">{p.id.slice(0, 8)}…</small>
                        </td>
                        <td>
                          {p.cluster_id.toUpperCase()}
                          <small>{p.namespace}</small>
                        </td>
                        <td>
                          <span className="phase">{p.kubernetes_phase}</span>
                        </td>
                        <td>
                          <Badge status={p.placement_status} />
                          <small>{p.node || 'Node 미확정'}</small>
                        </td>
                        <td>
                          <Badge status={p.relation_status} />
                          <small>{p.gpu || 'GPU 미확정'}</small>
                        </td>
                        <td>
                          <Badge status={p.activity_status} />
                        </td>
                        <td>
                          <Link className="text-link" to={`/analyses/new?pod=${p.id}`}>
                            이 Pod 조사
                            <ArrowUpRight size={14} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!podRows.length && <Empty />}
              </div>
              <div className="table-footer">
                관계 유효 구간 2026.09.16 14:10 ≤ t &lt; 14:15 KST · 현재 예시 관계
              </div>
            </Panel>
          )}
          <div className="two-column">
            <Panel title="관계의 의미">
              <div className="panel-body">
                <h3>활동 0 ≠ 연결 해제</h3>
                <p className="muted">
                  GPU 활동이 없더라도 관측된 관계는 유지됩니다. 공유 GPU의 전체 활동을 각 Pod의
                  사용량으로 복제하지 않습니다.
                </p>
                <TextLink to="/knowledge?item=kb-mapping&revision=1">연결 관계 가이드</TextLink>
              </div>
            </Panel>
            <Panel title="할당 이력이 필요하다면">
              <div className="panel-body">
                <h3>기간별 할당·활동 분석</h3>
                <p className="muted">
                  현재 매핑과 기간 GPU-hours를 구분하고, 확인 가능한 구간만 집계합니다.
                </p>
                <TextLink to="/reports">운영 보고서 만들기</TextLink>
              </div>
            </Panel>
          </div>
        </>
      )}
      {view === 'quality' && (
        <>
          <div className="quality-banner">
            <span className="quality-icon">
              <Radio size={25} />
            </span>
            <div>
              <h2>연결되어 있어도, 모든 분석이 준비된 것은 아닙니다.</h2>
              <p>CPC-2 일부 target·동시점 GPU ↔ Pod UID 확인과 장기 이력 검증을 구분합니다.</p>
            </div>
            <Badge status="partial" />
          </div>
          <Panel
            title="데이터 소스 수신 상태"
            description="연결 · 원본 갱신 · 분석 입력을 각각 확인합니다."
            action={<TextLink to="/settings/data">데이터 연결</TextLink>}
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>소스</th>
                    <th>범위</th>
                    <th>연결 상태</th>
                    <th>원본 시각 / 수신 시각</th>
                    <th>분석 입력 충분성</th>
                    <th>부족 입력</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    [
                      'GPU Exporter',
                      'CPC-2 일부 target',
                      'ready',
                      '14:14:55 / 14:14:58',
                      'partial',
                      '장기 활동·전력 이력',
                    ],
                    [
                      'Kubernetes State',
                      'CPC-2 일부 Namespace',
                      'ready',
                      '14:14:50 / 14:14:56',
                      'partial',
                      '과거 Pod UID 관계',
                    ],
                    [
                      'Loki 로그',
                      'CPC-2',
                      'blocked',
                      '마지막 수신 미확인',
                      'blocked',
                      '최종 재배포 후 최신 수신',
                    ],
                    [
                      '관측 직접 경로',
                      'CPC-1',
                      'blocked',
                      '전환 검증 대기',
                      'blocked',
                      '직접 수집 경로 검증',
                    ],
                  ]
                    .filter((r) =>
                      app.scope.clusters.some((c) => r[1].toLowerCase().includes(c.cluster_id)),
                    )
                    .map((r) => (
                      <tr key={r[0]}>
                        <td>
                          <b>{r[0]}</b>
                        </td>
                        <td>{r[1]}</td>
                        <td>
                          <Badge status={r[2]} label={r[2] === 'ready' ? '연결 확인' : '미확인'} />
                        </td>
                        <td>{r[3]}</td>
                        <td>
                          <Badge status={r[4]} />
                        </td>
                        <td>{r[5]}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="분석별 필요한 입력"
            description="연결 성공을 분석 준비 완료로 확대하지 않습니다."
          >
            <div className="readiness-grid">
              {[
                [
                  'R01',
                  '알려진 오류 조사',
                  'partial',
                  'GPU UUID·오류 시각 확보, 원본 로그 추가 필요',
                ],
                ['R03', 'Pod → GPU 관계', 'partial', '동시점 UID 확인, 과거 관계는 미확인'],
                ['O02', '할당 시간', 'blocked', '할당 episode의 전체 구간 이력 필요'],
                ['O09', 'GPU 에너지', 'blocked', '기간 내 실제 전력·에너지 관측 필요'],
                ['O11', '관측 품질', 'ready', '소스별 마지막 수신과 누락 구간 확인'],
              ].map((r) => (
                <div className="readiness-item" key={r[0]}>
                  <span className="code-label">{r[0]}</span>
                  <div>
                    <h3>{r[1]}</h3>
                    <p>{r[3]}</p>
                  </div>
                  <Badge status={r[2]} />
                </div>
              ))}
            </div>
          </Panel>
          <Notice>
            위 상태는 명세 C04의 확인 범위를 반영한 데모입니다. 실환경 검수 결과 또는 실제 연결
            상태가 아닙니다.
          </Notice>
        </>
      )}
      {node && (
        <Modal title={`${node.name} · GPU 상세`} onClose={() => setSelected(null)} wide>
          <div className="stack">
            <div className="detail-top">
              <span className="big-icon">
                <Cpu size={30} />
              </span>
              <div>
                <h3>{node.model}</h3>
                <p>
                  {node.cluster_id.toUpperCase()} / Node UID: {node.id}
                </p>
              </div>
              <Badge status={node.status} />
            </div>
            <div className="gpu-selector">
              {Array.from({ length: 8 }, (_, i) => (
                <button key={i} className={i === gpu ? 'selected' : ''} onClick={() => setGpu(i)}>
                  <Cpu size={17} />
                  GPU {i}
                </button>
              ))}
            </div>
            <dl className="details">
              <dt>GPU UUID</dt>
              <dd className="mono">
                GPU-{node.id}-0{gpu}
              </dd>
              <dt>신원 품질</dt>
              <dd>예시 UUID · 모델 식별 확인</dd>
              <dt>원본 시각</dt>
              <dd>2026.09.16 {node.last_seen} KST</dd>
              <dt>관측 단위</dt>
              <dd>전용 물리 GPU</dd>
              <dt>활동 / VRAM</dt>
              <dd>
                {node.utilization ?? '미확인'} % / {node.memory ?? '미확인'} %
              </dd>
              <dt>평균 전력</dt>
              <dd>{node.power ?? '미확인'} W</dd>
            </dl>
            <Notice>
              GPU별 화면은 Node 관측 예시를 사용합니다. VRAM 점유를 연산 활동으로 해석하지 않습니다.
            </Notice>
            <div className="form-actions">
              <button
                className="button"
                onClick={() => {
                  app.ask(
                    `${node.cluster_id} / ${node.name} / GPU-${node.id}-0${gpu} · 2026.09.16 14:15 KST`,
                  );
                  setSelected(null);
                }}
              >
                <Sparkles size={15} />
                선택 GPU 질문
              </button>
              <Link className="button primary" to={`/analyses/new?node=${node.id}&gpu=${gpu}`}>
                <ScanSearch size={16} />
                조사 시작
              </Link>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
function Meter({ value, pale = false }: { value: number | null; pale?: boolean }) {
  return value === null ? (
    <span className="muted">—</span>
  ) : (
    <div className={`meter ${pale ? 'pale' : ''}`}>
      <span style={{ width: `${value}%` }} />
      <b>{value}%</b>
    </div>
  );
}
