import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Field, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, JobRows, More, QueryState } from '../components/live';
import { localInput, queryPath, str, topicId, topics, useCommand, useList } from '../lib/live';
import { preciseRange, scopeLabel } from '../lib/domain';
import { useApp } from '../lib/store';
export const reportTabs = [
  { to: '/reports', label: '보고서 이력' },
  { to: '/reports/new', label: '새 보고서' },
  { to: '/schedules', label: '정기 일정' },
];
export function Reports() {
  const app = useApp();
  const [filterParams, setFilterParams] = useSearchParams();
  const topic = filterParams.get('topic') || '';
  const setTopic = (value: string) => {
    const next = new URLSearchParams(filterParams);
    next.set('topic', value);
    setFilterParams(next);
  };
  const q = useList(
    app.ready ? queryPath('/reports', { scope: app.scope, topic_id: topic, limit: 30 }) : null,
    true,
  );
  return (
    <div className="page">
      <PageHead
        eyebrow="OPERATIONS REPORTS"
        title="운영 분석·보고서"
        description="저장된 근거를 바탕으로 운영 분석을 요청하고 결과를 확인합니다."
        actions={
          <Link className="button primary" to="/reports/new">
            새 보고서
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <Panel title="보고서 목록">
        <div className="live-toolbar">
          <Field label="분석 주제">
            <select value={topic} onChange={(e) => setTopic(e.target.value)}>
              <option value="">전체 주제</option>
              {topics.map((t, i) => (
                <option value={topicId(i)} key={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <QueryState query={q} empty={!q.items.length}>
          <JobRows items={q.items} />
        </QueryState>
        <More query={q} />
      </Panel>
    </div>
  );
}
export function ReportForm() {
  const app = useApp(),
    navigate = useNavigate(),
    [params] = useSearchParams(),
    cmd = useCommand();
  const [selected, setSelected] = useState(['O01']),
    [group, setGroup] = useState('cluster'),
    [scheduled, setScheduled] = useState(params.get('schedule') === 'true'),
    [frequency, setFrequency] = useState('daily'),
    [localTime, setLocalTime] = useState('09:00'),
    [weekday, setWeekday] = useState(1),
    [day, setDay] = useState(1),
    [start, setStart] = useState(localInput(new Date(app.timeRange.start))),
    [end, setEnd] = useState(localInput(new Date(app.timeRange.end))),
    [compare, setCompare] = useState(false),
    [compareStart, setCompareStart] = useState(''),
    [compareEnd, setCompareEnd] = useState('');
  const [actionRefs, setActionRefs] = useState(''),
    [resourceName, setResourceName] = useState(''),
    [resourceUnit, setResourceUnit] = useState(''),
    [resourceCluster, setResourceCluster] = useState(app.scope.clusters[0]?.cluster_id || '');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const template = {
        scope: app.scope,
        topic_ids: selected,
        group_by: [group],
        ...(actionRefs.trim()
          ? {
              action_record_ids: actionRefs
                .split('\n')
                .map((v) => v.trim())
                .filter(Boolean),
            }
          : {}),
        ...(resourceName.trim()
          ? {
              resource_selectors: [
                {
                  cluster_id: resourceCluster,
                  resource_name: resourceName.trim(),
                  unit: resourceUnit.trim(),
                },
              ],
            }
          : {}),
      };
      const body = scheduled
        ? {
            enabled: true,
            report_spec: template,
            frequency,
            local_time: localTime,
            timezone: 'Asia/Seoul',
            period: (
              {
                daily: 'previous_complete_day',
                weekly: 'previous_complete_week',
                monthly: 'previous_complete_month',
              } as Record<string, string>
            )[frequency],
            ...(frequency === 'weekly' ? { weekday } : frequency === 'monthly' ? { day } : {}),
          }
        : {
            ...template,
            timezone: 'Asia/Seoul',
            time_range: preciseRange(start, end),
            ...(compare ? { comparison_range: preciseRange(compareStart, compareEnd) } : {}),
            ...(params.get('parent_job_id') ? { parent_job_id: params.get('parent_job_id') } : {}),
          };
      const result = await cmd.run(scheduled ? '/schedules' : '/reports', body, {
        idempotent: true,
      });
      if (result) {
        const id = str(result.job_id, str(result.id, str(result.schedule_id)));
        if (id) navigate(scheduled ? `/schedules/${id}` : `/jobs/${id}`);
        else {
          app.notify('서버가 요청을 처리했습니다. 목록에서 확인해 주세요.');
          navigate(scheduled ? '/schedules' : '/reports');
        }
      }
    } catch (e) {
      cmd.setError(e instanceof Error ? e.message : '입력값을 확인해 주세요.');
    }
  };
  return (
    <div className="page">
      <PageHead
        eyebrow="NEW REPORT"
        title="새 운영 보고서"
        description="분석 주제와 기간을 선택합니다. 접수된 작업은 작업 이력에서 추적할 수 있습니다."
      />
      <NavTabs items={reportTabs} />
      <form className="stack" onSubmit={submit}>
        <Panel title="분석 주제">
          <div className="live-check-grid">
            {topics.map((t, i) => (
              <label className="check" key={t}>
                <input
                  type="checkbox"
                  checked={selected.includes(topicId(i))}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, topicId(i)]
                        : selected.filter((x) => x !== topicId(i)),
                    )
                  }
                />
                <span>
                  <small>{topicId(i)}</small> {t}
                </span>
              </label>
            ))}
          </div>
        </Panel>
        <Panel title="범위와 실행 조건">
          <div className="live-padding stack">
            <Notice>{scopeLabel(app.scope)}</Notice>
            <details>
              <summary>조치 기록·자원 조건</summary>
              <div className="stack">
                <Field
                  label="조치 기록 ID"
                  hint="조치 전후 비교에 사용할 서버 기록 ID를 한 줄에 하나씩 입력합니다."
                >
                  <textarea
                    rows={2}
                    value={actionRefs}
                    onChange={(e) => setActionRefs(e.target.value)}
                  />
                </Field>
                <div className="form-grid">
                  <Field label="자원 CPC">
                    <select
                      value={resourceCluster}
                      onChange={(e) => setResourceCluster(e.target.value)}
                    >
                      {app.scope.clusters.map((c) => (
                        <option key={c.cluster_id}>{c.cluster_id}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="등록된 자원 이름">
                    <input value={resourceName} onChange={(e) => setResourceName(e.target.value)} />
                  </Field>
                  <Field label="자원 단위" hint="수집된 자원 카탈로그의 이름·단위를 사용합니다.">
                    <input
                      required={!!resourceName.trim()}
                      value={resourceUnit}
                      onChange={(e) => setResourceUnit(e.target.value)}
                    />
                  </Field>
                </div>
              </div>
            </details>
            <Field label="집계 기준">
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                {['cluster', 'model', 'node', 'namespace', 'pod', 'workload'].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </Field>
            <label className="check">
              <input
                type="checkbox"
                checked={scheduled}
                onChange={(e) => setScheduled(e.target.checked)}
              />
              정기 일정으로 등록
            </label>
            {scheduled ? (
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
                      required
                      type="time"
                      value={localTime}
                      onChange={(e) => setLocalTime(e.target.value)}
                    />
                  </Field>
                  {frequency === 'weekly' && (
                    <Field label="요일">
                      <select value={weekday} onChange={(e) => setWeekday(+e.target.value)}>
                        {['월', '화', '수', '목', '금', '토', '일'].map((d, i) => (
                          <option value={i + 1} key={d}>
                            {d}요일
                          </option>
                        ))}
                      </select>
                    </Field>
                  )}
                  {frequency === 'monthly' && (
                    <Field label="날짜">
                      <input
                        required
                        type="number"
                        min={1}
                        max={31}
                        value={day}
                        onChange={(e) => setDay(+e.target.value)}
                      />
                    </Field>
                  )}
                </div>
                <Notice>
                  직전에 완료된{' '}
                  {frequency === 'daily' ? '일' : frequency === 'weekly' ? '주' : '월'}을
                  분석합니다. 다음 실행 시각은 Backend에서 계산합니다.
                </Notice>
              </>
            ) : (
              <>
                <div className="form-grid">
                  <Field label="시작 시각 (KST)">
                    <input
                      required
                      type="datetime-local"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </Field>
                  <Field label="종료 시각 (KST)">
                    <input
                      required
                      type="datetime-local"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </Field>
                </div>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={compare}
                    onChange={(e) => setCompare(e.target.checked)}
                  />
                  이전 기간과 비교
                </label>
                {compare && (
                  <div className="form-grid">
                    <Field label="비교 시작 (KST)">
                      <input
                        required
                        type="datetime-local"
                        value={compareStart}
                        onChange={(e) => setCompareStart(e.target.value)}
                      />
                    </Field>
                    <Field label="비교 종료 (KST)">
                      <input
                        required
                        type="datetime-local"
                        value={compareEnd}
                        onChange={(e) => setCompareEnd(e.target.value)}
                      />
                    </Field>
                  </div>
                )}
              </>
            )}
          </div>
        </Panel>
        <CommandError error={cmd.error} />
        <div className="form-actions">
          <Link className="button" to="/reports">
            돌아가기
          </Link>
          <button
            className="button primary"
            disabled={cmd.busy || !selected.length || !app.canOperate}
          >
            {cmd.busy ? '접수 확인 중…' : scheduled ? '일정 등록' : '보고서 요청'}
          </button>
        </div>
      </form>
    </div>
  );
}
