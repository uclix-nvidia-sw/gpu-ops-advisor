import { ArrowLeft, ArrowUpRight, Plus, ScanSearch } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Empty, Field, Notice, PageHead, Panel, SearchBox } from '../components/ui';
import { assets, pods, purposes } from '../data/fixtures';
import { formatDate, inScope, preciseRange, scopeLabel } from '../lib/domain';
import { createJob } from '../lib/jobs';
import { useApp, useDatabase } from '../lib/store';
export function Cases() {
  const { db } = useDatabase();
  const app = useApp();
  const [tab, setTab] = useState('incidents');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const incidents =
    db?.incidents.filter(
      (i) =>
        inScope(app.scope, i.cluster_id) &&
        `${i.title} ${i.node} ${i.label}`.toLowerCase().includes(search.toLowerCase()) &&
        (status === 'all' || status === i.status),
    ) || [];
  const direct =
    db?.jobs.filter(
      (j) =>
        j.kind === 'rca' &&
        !j.incident_id &&
        j.scope.clusters.some((c) => inScope(app.scope, c.cluster_id)) &&
        j.title.includes(search),
    ) || [];
  return (
    <div className="page">
      <PageHead
        eyebrow="ROOT CAUSE ANALYSIS"
        title="RCA 조사"
        description="관측된 신호에서 시작해 사실과 원인 후보를 차근차근 확인합니다."
        actions={
          <Link className="button primary" to="/analyses/new">
            <Plus size={17} />새 조사 요청
          </Link>
        }
      />
      <div className="tabs">
        <button className={tab === 'incidents' ? 'active' : ''} onClick={() => setTab('incidents')}>
          사건 <span className="counter">{db?.incidents.length || 0}</span>
        </button>
        <button className={tab === 'direct' ? 'active' : ''} onClick={() => setTab('direct')}>
          직접 요청
        </button>
      </div>
      <div className="toolbar">
        <SearchBox
          value={search}
          onChange={setSearch}
          placeholder="사건, 대상 또는 조사 제목 검색"
        />
        {tab === 'incidents' && (
          <select
            aria-label="사건 상태 필터"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">모든 사건 상태</option>
            <option value="open">열림</option>
            <option value="investigating">조사 중</option>
            <option value="resolved">해결됨</option>
            <option value="closed">종결</option>
          </select>
        )}
      </div>
      <Panel>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{tab === 'incidents' ? '사건 / 관측 신호' : '조사 제목'}</th>
                <th>대상</th>
                <th>접수 / 발생 시각</th>
                {tab === 'incidents' && <th>사건 상태</th>}
                <th>실행 상태</th>
                <th>산출 상태</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tab === 'incidents'
                ? incidents.map((i) => {
                    const j = db?.jobs.find((j) => j.id === i.analysis_id);
                    return (
                      <tr key={i.id}>
                        <td>
                          <Link to={`/incidents/${i.id}`}>
                            <b>{i.title}</b>
                            <small>{i.label}</small>
                          </Link>
                        </td>
                        <td>
                          {i.node}
                          <small>{i.cluster_id.toUpperCase()}</small>
                        </td>
                        <td>{formatDate(i.created_at)}</td>
                        <td>
                          <Badge status={i.status} />
                        </td>
                        <td>
                          {j ? (
                            <Link to={`/jobs/${j.id}`}>
                              <Badge status={j.status} />
                            </Link>
                          ) : (
                            <span className="muted">조사 미접수</span>
                          )}
                        </td>
                        <td>
                          <Badge status={j?.result_status || null} />
                        </td>
                        <td>
                          <Link className="text-link" to={`/incidents/${i.id}`}>
                            상세
                            <ArrowUpRight size={14} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                : direct.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <b>{j.title}</b>
                        <small className="mono">{j.id.slice(0, 8)}</small>
                      </td>
                      <td>{j.target}</td>
                      <td>{formatDate(j.created_at)}</td>
                      <td>
                        <Badge status={j.status} />
                      </td>
                      <td>
                        <Badge status={j.result_status} />
                      </td>
                      <td>
                        <Link
                          className="text-link"
                          to={j.status === 'succeeded' ? `/analyses/${j.id}` : `/jobs/${j.id}`}
                        >
                          {j.status === 'succeeded' ? '결과 보기' : '진행 보기'}
                          <ArrowUpRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
          {(tab === 'incidents' ? !incidents.length : !direct.length) && (
            <Empty
              title={search ? '검색 결과가 없습니다.' : '직접 요청한 조사가 없습니다.'}
              description="대상을 선택하고 새 RCA 조사를 요청해 보세요."
              action={
                <Link to="/analyses/new" className="button">
                  새 조사 요청
                </Link>
              }
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
export function AnalysisForm() {
  const app = useApp();
  const { mutate, db } = useDatabase();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const parent = db?.jobs.find((j) => j.id === params.get('parent'));
  const pod = pods.find((p) => p.id === params.get('pod') || p.name === parent?.target);
  const incident = db?.incidents.find((i) => i.id === params.get('incident'));
  const node = assets.find(
    (a) => a.id === params.get('node') || a.name === incident?.node || a.name === parent?.target,
  );
  const [kind, setKind] = useState(pod ? 'pod' : params.has('gpu') ? 'gpu' : 'node');
  const [target, setTarget] = useState(pod?.id || node?.id || '');
  const [symptom, setSymptom] = useState(incident?.title || String(parent?.request.symptom || ''));
  const [chosen, setChosen] = useState<string[]>(
    pod ? ['R03', 'R04'] : params.has('recheck') ? ['R01', 'R09'] : ['R01'],
  );
  const [start, setStart] = useState(
    params.has('recheck') ? '2026-09-16T14:15' : '2026-09-16T13:15',
  );
  const [end, setEnd] = useState(params.has('recheck') ? '2026-09-16T15:15' : '2026-09-16T14:15');
  const [incidentTime, setIncidentTime] = useState(pod ? '2026-09-16T14:15' : '2026-09-16T13:42');
  const [gpu, setGpu] = useState(params.get('gpu') || '0');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const submitLock = useRef(false);
  const choices =
    kind === 'pod'
      ? pods.filter((p) => inScope(app.scope, p.cluster_id, p.namespace))
      : assets.filter((a) => inScope(app.scope, a.cluster_id));
  const selectedPod = kind === 'pod' ? pods.find((p) => p.id === target) : undefined;
  const requestScope = selectedPod
    ? { clusters: [{ cluster_id: selectedPod.cluster_id, namespaces: [selectedPod.namespace] }] }
    : app.scope;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitLock.current) return;
    setError('');
    try {
      if (app.role !== 'operator') throw new Error('새 조사는 운영자 역할에서 요청할 수 있습니다.');
      if (!target || !choices.some((c) => c.id === target))
        throw new Error('현재 범위에 속한 조사 대상을 선택해 주세요.');
      if (!symptom.trim()) throw new Error('관측한 증상을 입력해 주세요.');
      if (!chosen.length) throw new Error('조사 목적을 하나 이상 선택해 주세요.');
      const range = preciseRange(start, end);
      const selected = choices.find((c) => c.id === target)!;
      const p = pods.find((p) => p.id === target);
      const targetDTO =
        kind === 'pod'
          ? {
              kind,
              cluster_id: selected.cluster_id,
              namespace: p!.namespace,
              pod_name: p!.name,
              pod_uid: p!.id,
            }
          : kind === 'gpu'
            ? { kind, cluster_id: selected.cluster_id, gpu_uuid: `GPU-${target}-0${gpu}` }
            : { kind, cluster_id: selected.cluster_id, node_uid: target };
      submitLock.current = true;
      setBusy(true);
      const job = createJob({
        kind: 'rca',
        title: `${selected.name} · ${symptom.trim()}`,
        scope: structuredClone(requestScope),
        time_range: range,
        target: selected.name,
        purpose_ids: chosen,
        incident_id: incident?.id,
        parent_job_id: params.get('parent') || undefined,
        request: {
          target: targetDTO,
          symptom: symptom.trim(),
          purpose_ids: chosen,
          timezone: 'Asia/Seoul',
          incident_time: `${incidentTime}:00+09:00`,
        },
      });
      await mutate((d) => {
        d.jobs.unshift(job);
        if (incident) {
          const i = d.incidents.find((i) => i.id === incident.id)!;
          i.analysis_id = job.id;
          i.version++;
        }
      });
      app.notify('데모 조사 요청이 접수되었습니다.');
      navigate(`/jobs/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
      submitLock.current = false;
      setBusy(false);
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  };
  return (
    <div className="page form-page">
      <Link className="back-link" to="/cases">
        <ArrowLeft size={15} />
        조사 목록
      </Link>
      <PageHead
        eyebrow="NEW INVESTIGATION"
        title={params.has('recheck') ? '현재 상태 재확인' : '새 RCA 조사 요청'}
        description="조사할 대상과 기간을 고정하고, 확인하려는 증상을 알려주세요."
      />
      <form onSubmit={submit}>
        <div className="form-layout">
          <div className="stack">
            <Panel title="01  조사 대상" description="대상 종류와 소속을 함께 확인합니다.">
              <div className="panel-body stack">
                <div className="target-types">
                  {[
                    ['node', 'Node'],
                    ['gpu', 'GPU'],
                    ['pod', 'Pod'],
                  ].map(([v, l]) => (
                    <button
                      type="button"
                      key={v}
                      className={kind === v ? 'selected' : ''}
                      onClick={() => {
                        setKind(v);
                        setTarget('');
                      }}
                    >
                      <ScanSearch size={19} />
                      {l}
                    </button>
                  ))}
                </div>
                <Field label={`${kind === 'pod' ? 'Pod 이름 / UID' : 'Node'} *`}>
                  <select required value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="">대상을 선택하세요</option>
                    {choices.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.cluster_id.toUpperCase()} / {a.name}
                        {'namespace' in a ? ` / ${a.namespace} / ${a.id.slice(0, 8)}` : ''}
                      </option>
                    ))}
                  </select>
                </Field>
                {kind === 'gpu' && (
                  <Field label="GPU UUID *">
                    <select value={gpu} onChange={(e) => setGpu(e.target.value)}>
                      {Array.from({ length: 8 }, (_, i) => (
                        <option key={i} value={i}>
                          GPU {i} · GPU-{target}-0{i}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {kind === 'pod' && (
                  <Notice>
                    Pod UID를 기준으로 조사합니다. Node와 GPU 관계가 미확정이어도 요청할 수
                    있습니다.
                  </Notice>
                )}
                {incident && (
                  <Notice>
                    연결 사건: {incident.label} · 현재 상태 {incident.status}
                  </Notice>
                )}
              </div>
            </Panel>
            <Panel title="02  조사 기간·증상">
              <div className="panel-body stack">
                <div className="form-grid">
                  <Field label="시작 시각 (KST) *">
                    <input
                      required
                      type="datetime-local"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </Field>
                  <Field label="종료 시각 (KST) *">
                    <input
                      required
                      type="datetime-local"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </Field>
                </div>
                <Field label="사건·관계 기준 시각 (KST)">
                  <input
                    required
                    type="datetime-local"
                    value={incidentTime}
                    onChange={(e) => setIncidentTime(e.target.value)}
                  />
                </Field>
                <Field
                  label="관측한 증상 *"
                  hint="오류 코드, 작업 변화, 확인하고 싶은 내용을 구체적으로 적어주세요."
                >
                  <textarea
                    required
                    rows={4}
                    value={symptom}
                    onChange={(e) => setSymptom(e.target.value)}
                    placeholder="예: GPU 응답 중단 이후 작업이 멈췄습니다. 당시 작업 관계와 오류 원인을 확인하고 싶습니다."
                  />
                </Field>
              </div>
            </Panel>
            <Panel title="03  조사 목적" description="필요한 목적을 여러 개 선택할 수 있습니다.">
              <div className="topic-checkboxes">
                {purposes.map((p, i) => {
                  const id = `R${String(i + 1).padStart(2, '0')}`;
                  return (
                    <label className="topic-check" key={id}>
                      <input
                        type="checkbox"
                        checked={chosen.includes(id)}
                        onChange={(e) =>
                          setChosen((s) =>
                            e.target.checked ? [...s, id] : s.filter((x) => x !== id),
                          )
                        }
                      />
                      <span className="code-label">{id}</span>
                      <span>{p}</span>
                    </label>
                  );
                })}
              </div>
            </Panel>
          </div>
          <aside className="form-summary">
            <span className="summary-icon">
              <ScanSearch size={24} />
            </span>
            <h2>조사 요청 요약</h2>
            <dl>
              <dt>관측 범위</dt>
              <dd>{scopeLabel(requestScope)}</dd>
              <dt>대상</dt>
              <dd>{choices.find((a) => a.id === target)?.name || '선택 필요'}</dd>
              <dt>기간</dt>
              <dd>
                {start.replace('T', ' ')}
                <br />~ {end.replace('T', ' ')}
              </dd>
              <dt>선택 목적</dt>
              <dd>{chosen.join(' · ') || '선택 필요'}</dd>
              <dt>처리 방식</dt>
              <dd>비동기 RCA 작업 · 데모</dd>
            </dl>
            <Notice>
              실제 장비 조치는 수행하지 않습니다. 조사 결과에서 근거와 다음 확인 사항을 검토하세요.
            </Notice>
            {error && (
              <div ref={errorRef} tabIndex={-1} className="error" role="alert">
                {error}
              </div>
            )}
            <button
              disabled={busy || app.role !== 'operator'}
              className="button primary full-width"
              type="submit"
            >
              {busy ? '접수 중…' : '조사 요청'}
              <ArrowUpRight size={16} />
            </button>
            {app.role !== 'operator' && <p className="muted">운영자 역할이 필요합니다.</p>}
          </aside>
        </div>
      </form>
    </div>
  );
}
