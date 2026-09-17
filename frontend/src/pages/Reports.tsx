import {
  ArrowLeft,
  ArrowUpRight,
  Boxes,
  CalendarClock,
  ChartNoAxesCombined,
  Check,
  FileChartColumn,
  History,
  Zap,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Empty, Field, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { topicId, topics } from '../data/fixtures';
import {
  calendarRange,
  formatDate,
  inScope,
  nextSchedule,
  preciseRange,
  scopeLabel,
} from '../lib/domain';
import { createJob } from '../lib/jobs';
import { useApp, useDatabase } from '../lib/store';
const groups = [
  {
    title: '관측·용량',
    description: '인프라 변화와 배치 여유를 확인합니다.',
    icon: Boxes,
    topics: [0, 6, 10],
    color: 'blue',
  },
  {
    title: '할당·활동',
    description: '할당된 자원이 어떻게 활동하는지 살펴봅니다.',
    icon: ChartNoAxesCombined,
    topics: [1, 2, 3, 7],
    color: 'green',
  },
  {
    title: '반복 사건·조치',
    description: '사건의 반복과 조치 전후 변화를 비교합니다.',
    icon: History,
    topics: [4, 5, 9],
    color: 'purple',
  },
  {
    title: '에너지',
    description: '실제 관측된 전력과 에너지를 분석합니다.',
    icon: Zap,
    topics: [8],
    color: 'amber',
  },
];
export const reportTabs = [
  { to: '/reports', label: '운영 분석·보고서' },
  { to: '/schedules', label: '정기 일정' },
];
export function Reports() {
  const { db } = useDatabase();
  const app = useApp();
  const [chosen, setChosen] = useState(['O01', 'O03', 'O11']);
  const rows =
    db?.jobs.filter(
      (j) => j.kind === 'report' && j.scope.clusters.some((c) => inScope(app.scope, c.cluster_id)),
    ) || [];
  return (
    <div className="page">
      <PageHead
        eyebrow="ANALYTICS & REPORTS"
        title="운영 분석·보고서"
        description="궁금한 주제를 선택하면, 관측 근거를 바탕으로 운영 현황을 정리합니다."
        actions={
          <Link className="button" to="/schedules">
            <CalendarClock size={16} />
            정기 일정 관리
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <div className="section-title">
        <h2>어떤 주제를 살펴볼까요?</h2>
        <span>여러 주제를 함께 선택할 수 있습니다.</span>
      </div>
      <div className="report-topics">
        {groups.map((g) => (
          <Panel key={g.title} className="topic-card">
            <div className={`topic-icon ${g.color}`}>
              <g.icon size={23} />
            </div>
            <h2>{g.title}</h2>
            <p>{g.description}</p>
            <div className="topic-list">
              {g.topics.map((i) => (
                <label key={i} className="check">
                  <input
                    type="checkbox"
                    checked={chosen.includes(topicId(i))}
                    onChange={(e) =>
                      setChosen((s) =>
                        e.target.checked ? [...s, topicId(i)] : s.filter((x) => x !== topicId(i)),
                      )
                    }
                  />
                  <span>{topics[i]}</span>
                  <small>{topicId(i)}</small>
                </label>
              ))}
            </div>
          </Panel>
        ))}
      </div>
      <div className="selection-bar">
        <div>
          <span className="selection-check">
            <Check size={17} />
          </span>
          <b>{chosen.length}개 주제 선택</b>
          <span>기간과 상세 조건은 다음 단계에서 설정합니다.</span>
        </div>
        <Link
          className={`button primary ${!chosen.length ? 'disabled' : ''}`}
          aria-disabled={!chosen.length}
          to={`/reports/new?topics=${chosen.join(',')}`}
          onClick={(e) => {
            if (!chosen.length) e.preventDefault();
          }}
        >
          보고서 만들기
          <ArrowUpRight size={17} />
        </Link>
      </div>
      <Panel title="최근 보고서" description="저장된 대상·기간·수치를 유지하는 보고서입니다.">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>보고서</th>
                <th>선택 주제</th>
                <th>생성 시각 (KST)</th>
                <th>실행 상태</th>
                <th>산출 상태</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link to={j.status === 'succeeded' ? `/reports/${j.id}` : `/jobs/${j.id}`}>
                      <b>{j.title}</b>
                      <small>{scopeLabel(j.scope)}</small>
                    </Link>
                  </td>
                  <td>{j.topic_ids?.join(' · ')}</td>
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
                      to={j.status === 'succeeded' ? `/reports/${j.id}` : `/jobs/${j.id}`}
                    >
                      열기
                      <ArrowUpRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty />}
        </div>
      </Panel>
    </div>
  );
}
export function ReportForm() {
  const app = useApp();
  const { mutate, db } = useDatabase();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const parent = db?.jobs.find((j) => j.id === params.get('parent'));
  const [chosen, setChosen] = useState<string[]>(
    params
      .get('topics')
      ?.split(',')
      .filter((t) => topics.some((_, i) => topicId(i) === t)) ||
      parent?.topic_ids || ['O01', 'O11'],
  );
  const [start, setStart] = useState('2026-09-16');
  const [end, setEnd] = useState('2026-09-16');
  const [precise, setPrecise] = useState(false);
  const [group, setGroup] = useState('cluster');
  const [mode, setMode] = useState('once');
  const [name, setName] = useState('GPU 운영 보고서');
  const [frequency, setFrequency] = useState('daily');
  const [localTime, setLocalTime] = useState('09:00');
  const [weekday, setWeekday] = useState(1);
  const [day, setDay] = useState(1);
  const [compare, setCompare] = useState(false);
  const [compareStart, setCompareStart] = useState('2026-09-15');
  const [compareEnd, setCompareEnd] = useState('2026-09-15');
  const [resource, setResource] = useState('');
  const [action, setAction] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const errRef = useRef<HTMLDivElement>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (lock.current) return;
    setError('');
    try {
      if (app.role !== 'operator') throw new Error('보고서는 운영자 역할에서 요청할 수 있습니다.');
      if (!chosen.length) throw new Error('분석 주제를 하나 이상 선택해 주세요.');
      if (!name.trim()) throw new Error('보고서 이름을 입력해 주세요.');
      const range = precise ? preciseRange(start, end) : calendarRange(start, end);
      const comparison = compare ? calendarRange(compareStart, compareEnd) : undefined;
      lock.current = true;
      setBusy(true);
      if (mode === 'scheduled') {
        const id = crypto.randomUUID();
        await mutate((d) =>
          d.schedules.unshift({
            id,
            name,
            frequency,
            local_time: localTime,
            weekday,
            day,
            timezone: 'Asia/Seoul',
            enabled: true,
            revision: 1,
            scope: structuredClone(app.scope),
            topic_ids: chosen,
            next_run: nextSchedule(frequency, localTime, weekday, day),
            report_conditions: {
              group_by: group,
              comparison_range: comparison,
              resource_selectors: resource
                ? [{ cluster_id: resource, resource_name: 'nvidia.com/gpu', unit: 'physical_gpu' }]
                : [],
              action_record_ids: action ? [action] : [],
            },
          }),
        );
        app.notify('데모 정기 일정이 저장되었습니다. 실제 예약 실행은 백엔드 연결 후 가능합니다.');
        navigate(`/schedules/${id}`);
      } else {
        const job = createJob({
          kind: 'report',
          title: name,
          scope: structuredClone(app.scope),
          time_range: range,
          topic_ids: chosen,
          parent_job_id: parent?.id,
          request: {
            group_by: group,
            comparison_range: comparison,
            resource_selectors: resource
              ? [{ cluster_id: resource, resource_name: 'nvidia.com/gpu', unit: 'physical_gpu' }]
              : undefined,
            action_record_ids: action ? [action] : [],
            timezone: 'Asia/Seoul',
          },
        });
        await mutate((d) => d.jobs.unshift(job));
        app.notify('데모 보고서 요청이 접수되었습니다.');
        navigate(`/jobs/${job.id}`);
      }
    } catch (e) {
      setError((e as Error).message);
      lock.current = false;
      setBusy(false);
      requestAnimationFrame(() => errRef.current?.focus());
    }
  };
  return (
    <div className="page form-page">
      <Link className="back-link" to="/reports">
        <ArrowLeft size={15} />
        운영 분석·보고서
      </Link>
      <PageHead
        eyebrow="NEW REPORT"
        title="보고서 요청"
        description="분석 범위와 주제를 확인하고, 한 번 또는 정기적으로 실행하도록 설정하세요."
      />
      <form onSubmit={submit}>
        <div className="form-layout">
          <div className="stack">
            <Panel title="01  기본 조건">
              <div className="panel-body stack">
                <Field label="보고서 이름 *">
                  <input required value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <div className="form-grid">
                  <Field label="시작일 / 시각 *">
                    <input
                      required
                      type={precise ? 'datetime-local' : 'date'}
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </Field>
                  <Field label="종료일 / 시각 *">
                    <input
                      required
                      type={precise ? 'datetime-local' : 'date'}
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </Field>
                </div>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={precise}
                    onChange={(e) => {
                      setPrecise(e.target.checked);
                      setStart(
                        e.target.checked ? start.slice(0, 10) + 'T00:00' : start.slice(0, 10),
                      );
                      setEnd(e.target.checked ? end.slice(0, 10) + 'T23:59' : end.slice(0, 10));
                    }}
                  />
                  정밀 시각으로 지정
                </label>
                <small className="muted">
                  {precise
                    ? '선택한 시작 시각 이상, 종료 시각 미만을 분석합니다.'
                    : '시작일 00:00부터 종료일 다음 날 00:00 미만 · 같은 날 보고서도 가능합니다.'}{' '}
                  Asia/Seoul
                </small>
                <Field label="집계 단위">
                  <select value={group} onChange={(e) => setGroup(e.target.value)}>
                    {['cluster', 'model', 'node', 'namespace', 'pod', 'workload'].map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                </Field>
              </div>
            </Panel>
            <Panel title="02  분석 주제">
              <div className="topic-checkboxes">
                {topics.map((t, i) => (
                  <label key={t} className="topic-check">
                    <input
                      type="checkbox"
                      checked={chosen.includes(topicId(i))}
                      onChange={(e) =>
                        setChosen((s) =>
                          e.target.checked ? [...s, topicId(i)] : s.filter((x) => x !== topicId(i)),
                        )
                      }
                    />
                    <span className="code-label">{topicId(i)}</span>
                    {t}
                  </label>
                ))}
              </div>
              <div className="panel-body">
                <details>
                  <summary>비교 기간·자원·조치 연결 조건</summary>
                  <div className="stack advanced-fields">
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={compare}
                        onChange={(e) => setCompare(e.target.checked)}
                      />
                      비교 기간 추가
                    </label>
                    {compare && (
                      <div className="form-grid">
                        <Field label="비교 시작일">
                          <input
                            required
                            type="date"
                            value={compareStart}
                            onChange={(e) => setCompareStart(e.target.value)}
                          />
                        </Field>
                        <Field label="비교 종료일">
                          <input
                            required
                            type="date"
                            value={compareEnd}
                            onChange={(e) => setCompareEnd(e.target.value)}
                          />
                        </Field>
                      </div>
                    )}
                    {chosen.includes('O07') && (
                      <Field
                        label="O07 자원 종류"
                        hint="단위가 확인된 예시 카탈로그만 선택할 수 있습니다."
                      >
                        <select value={resource} onChange={(e) => setResource(e.target.value)}>
                          <option value="">전체 자원 · 미확인 단위는 보류</option>
                          {app.scope.clusters.map((c) => (
                            <option key={c.cluster_id} value={c.cluster_id}>
                              {c.cluster_id} / nvidia.com/gpu / physical_gpu
                            </option>
                          ))}
                        </select>
                      </Field>
                    )}
                    {chosen.includes('O10') && (
                      <>
                        <Field label="O10 실제 조치 기록">
                          <select value={action} onChange={(e) => setAction(e.target.value)}>
                            <option value="">조치 미연결 · 일반 기간 비교</option>
                            {db?.reviews
                              .filter((r) => r.type === 'action')
                              .map((r) => (
                                <option value={r.id} key={r.id}>
                                  {r.target} · {r.content}
                                </option>
                              ))}
                          </select>
                        </Field>
                        <Notice>
                          분석 기간은 조치 후, 비교 기간은 조치 전입니다. 조치 기록만으로 인과를
                          확정하지 않습니다.
                        </Notice>
                      </>
                    )}
                  </div>
                </details>
              </div>
            </Panel>
            <Panel title="03  실행 방식">
              <div className="panel-body stack">
                <div className="segmented">
                  <button
                    type="button"
                    className={mode === 'once' ? 'active' : ''}
                    onClick={() => setMode('once')}
                  >
                    한 번 실행
                  </button>
                  <button
                    type="button"
                    className={mode === 'scheduled' ? 'active' : ''}
                    onClick={() => setMode('scheduled')}
                  >
                    정기 실행
                  </button>
                </div>
                {mode === 'scheduled' && (
                  <>
                    <div className="form-grid">
                      <Field label="반복 주기">
                        <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                          <option value="daily">매일</option>
                          <option value="weekly">매주</option>
                          <option value="monthly">매월</option>
                        </select>
                      </Field>
                      <Field label="실행 시각 (KST)">
                        <input
                          type="time"
                          required
                          value={localTime}
                          onChange={(e) => setLocalTime(e.target.value)}
                        />
                      </Field>
                      {frequency === 'weekly' && (
                        <Field label="실행 요일">
                          <select
                            value={weekday}
                            onChange={(e) => setWeekday(Number(e.target.value))}
                          >
                            {['일', '월', '화', '수', '목', '금', '토'].map((d, i) => (
                              <option value={i} key={i}>
                                {d}요일
                              </option>
                            ))}
                          </select>
                        </Field>
                      )}
                      {frequency === 'monthly' && (
                        <Field label="실행 날짜 (없는 날짜는 말일)">
                          <input
                            type="number"
                            min="1"
                            max="31"
                            required
                            value={day}
                            onChange={(e) => setDay(Number(e.target.value))}
                          />
                        </Field>
                      )}
                    </div>
                    <Notice>
                      분석 구간:{' '}
                      {frequency === 'daily'
                        ? '직전 완료 일'
                        : frequency === 'weekly'
                          ? '직전 완료 주 (월요일~다음 월요일)'
                          : '직전 완료 월'}
                      . 위 날짜는 일회 실행에만 사용됩니다.
                    </Notice>
                  </>
                )}
              </div>
            </Panel>
          </div>
          <aside className="form-summary">
            <span className="summary-icon">
              <FileChartColumn size={25} />
            </span>
            <h2>보고서 요청 요약</h2>
            <dl>
              <dt>관측 범위</dt>
              <dd>{scopeLabel(app.scope)}</dd>
              <dt>분석 주제</dt>
              <dd>
                {chosen.length}개 · {chosen.join(', ')}
              </dd>
              <dt>집계 단위</dt>
              <dd>{group}</dd>
              <dt>실행 방식</dt>
              <dd>{mode === 'once' ? '한 번 실행' : `정기 실행 · ${localTime} KST`}</dd>
            </dl>
            <Notice>
              관측이 부족한 주제도 요청할 수 있습니다. 산출할 수 없는 값은 사유와 함께 표시됩니다.
            </Notice>
            {error && (
              <div className="error" role="alert" tabIndex={-1} ref={errRef}>
                {error}
              </div>
            )}
            <button
              className="button primary full-width"
              disabled={busy || app.role !== 'operator'}
            >
              {busy ? '접수 중…' : mode === 'once' ? '보고서 요청' : '정기 일정 저장'}
              <ArrowUpRight size={16} />
            </button>
            {app.role !== 'operator' && <p className="muted">운영자 역할이 필요합니다.</p>}
          </aside>
        </div>
      </form>
    </div>
  );
}
