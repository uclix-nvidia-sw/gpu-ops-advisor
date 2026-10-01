import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Field, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, JobRows, More, QueryState } from '../components/live';
import { queryPath, str, topicId, topics, useCommand, useList } from '../lib/live';
import { scopeLabel } from '../lib/domain';
import { groupLabel } from '../lib/report';
import { useReportListPosition } from '../lib/reportNavigation';
import {
  previousReportDay,
  reportDayRange,
  reportDaySummary,
  scheduleLabels,
  schedulePeriods,
  scheduleWindows,
} from '../lib/reportPeriod';
import { useApp } from '../lib/store';
export const reportTabs = [
  { to: '/reports', label: '보고서 이력' },
  { to: '/schedules', label: '정기 일정' },
  { to: '/operator-guide', label: '운영자 가이드' },
];
export function Reports() {
  const app = useApp();
  const [filterParams] = useSearchParams();
  const topic = filterParams.get('topic') || '';
  const finalOnly = filterParams.get('tab') === 'final';
  const q = useList(
    app.ready
      ? queryPath('/reports', {
          scope: app.scope,
          topic_id: topic,
          status: filterParams.get('status') || (finalOnly ? 'succeeded' : ''),
          limit: 30,
        })
      : null,
    true,
  );
  useReportListPosition(q.items);
  return (
    <div className="page">
      <PageHead
        eyebrow="OPERATIONS REPORTS"
        title="운영 분석·보고서"
        description="저장된 근거를 바탕으로 운영 분석을 요청하고 결과를 확인합니다."
        actions={
          <Link className="button primary" to="/reports/new">
            새 보고서 만들기
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <Panel title={finalOnly ? '공개된 Ops 최종 보고서' : '보고서 목록'}>
        {finalOnly && (
          <p>
            완료된 보고서를 바로 읽을 수 있습니다. 자료 부족·부분 분석 여부는 결과 품질에서
            확인하세요.
          </p>
        )}
        <ReportFilters />
        <QueryState query={q} empty={!q.items.length}>
          <JobRows items={q.items} preferResult />
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
  const [selected, setSelected] = useState(['O08']),
    [group, setGroup] = useState('namespace'),
    [purpose, setPurpose] = useState('namespace'),
    [scheduled, setScheduled] = useState(params.get('schedule') === 'true'),
    [frequency, setFrequency] = useState('daily'),
    [localTime, setLocalTime] = useState('09:00'),
    [weekday, setWeekday] = useState(1),
    [day, setDay] = useState(1),
    [start, setStart] = useState(previousReportDay()),
    [end, setEnd] = useState(previousReportDay()),
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
            period: schedulePeriods[frequency],
            ...(frequency === 'weekly' ? { weekday } : frequency === 'monthly' ? { day } : {}),
          }
        : {
            ...template,
            timezone: 'Asia/Seoul',
            time_range: reportDayRange(start, end),
            ...(compare ? { comparison_range: reportDayRange(compareStart, compareEnd) } : {}),
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
        description="기본 분석은 Namespace별 GPU 사용 분석입니다. 대상과 기간을 확인하고 요청하세요."
      />
      <NavTabs items={reportTabs} />
      <form className="stack" onSubmit={submit}>
        <Field label="보고서 목적">
          <select
            value={purpose}
            onChange={(e) => {
              setPurpose(e.target.value);
              if (e.target.value === 'namespace') {
                setSelected(['O08']);
                setGroup('namespace');
                setActionRefs('');
                setResourceName('');
                setResourceUnit('');
                setCompare(false);
              }
            }}
          >
            <option value="namespace">Namespace별 GPU 사용 분석</option>
            <option value="custom">직접 분석 조건 선택</option>
          </select>
        </Field>
        <Notice>
          {purpose === 'namespace'
            ? 'GPU 연결 시간과 연결 GPU의 평균 활동률을 분석합니다. 독점 할당량이나 회수 가능량을 뜻하지 않습니다.'
            : '분석 주제마다 필요한 데이터와 지원 집계가 다릅니다. 세부 설정에서 조건을 확인하세요.'}
        </Notice>
        <details open={purpose === 'custom'}>
          <summary>
            세부 분석 설정 · {selected.length}개 주제 · {groupLabel([group])}
          </summary>
          <Panel title="분석 주제">
            <div className="live-check-grid">
              {topics.map((t, i) => (
                <label className="check" key={t}>
                  <input
                    type="checkbox"
                    checked={selected.includes(topicId(i))}
                    onChange={(e) => {
                      setPurpose('custom');
                      setSelected(
                        e.target.checked
                          ? [...selected, topicId(i)]
                          : selected.filter((x) => x !== topicId(i)),
                      );
                    }}
                  />
                  <span>
                    <small>{topicId(i)}</small> {t}
                  </span>
                </label>
              ))}
            </div>
          </Panel>
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
            <select
              value={group}
              onChange={(e) => {
                setPurpose('custom');
                setGroup(e.target.value);
              }}
            >
              {['cluster', 'model', 'node', 'namespace', 'pod', 'workload'].map((v) => (
                <option key={v} value={v}>
                  {groupLabel([v])}
                </option>
              ))}
            </select>
          </Field>
        </details>
        <Panel title="범위와 실행 조건">
          <div className="live-padding stack">
            <Notice>{scopeLabel(app.scope)}</Notice>
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
                      {Object.entries(scheduleLabels).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
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
                  {scheduleWindows[frequency]} 전체를 분석합니다. 다음 실행 시각은 Backend에서
                  계산합니다.
                </Notice>
              </>
            ) : (
              <>
                <div className="form-grid">
                  <Field label="분석 시작일 (KST)">
                    <input
                      required
                      type="date"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </Field>
                  <Field label="분석 종료일 (포함, KST)">
                    <input
                      required
                      type="date"
                      min={start}
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
                    <Field label="비교 시작일 (KST)">
                      <input
                        required
                        type="date"
                        value={compareStart}
                        onChange={(e) => setCompareStart(e.target.value)}
                      />
                    </Field>
                    <Field label="비교 종료일 (포함, KST)">
                      <input
                        required
                        type="date"
                        min={compareStart}
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
        <Notice>
          <strong>요청 전 기간 확인 · 최소 1일(24시간), 최대 31일</strong>
          <p>
            {scheduled
              ? scheduleWindows[frequency] + ' 전체를 분석합니다.'
              : reportDaySummary(start, end)}
            {!scheduled && compare && (
              <>
                <br />
                비교: {reportDaySummary(compareStart, compareEnd)}
              </>
            )}
          </p>
          <p>
            수집 시작 전 서버가 실제 보고서 한도와 기간·대상의 초기 조회량을 검사합니다. 한도를
            넘으면 데이터를 조회하지 않고 사유를 남깁니다. 통과해도 데이터량·응답 제한에 따라 추가
            분할이나 부분 수집이 발생할 수 있으며 결과에서 수집 구간을 확인할 수 있습니다.
          </p>
        </Notice>
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

export function ReportFilters() {
  const [params, setParams] = useSearchParams();
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (key === 'status') next.delete('tab');
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };
  return (
    <div className="live-toolbar">
      <Field label="실행 상태">
        <select
          value={params.get('status') || (params.get('tab') === 'final' ? 'succeeded' : '')}
          onChange={(e) => filter('status', e.target.value)}
        >
          <option value="">전체 이력</option>
          <option value="succeeded">실행 완료</option>
          <option value="queued">대기 중</option>
          <option value="running">실행 중</option>
          <option value="retry_wait">재시도 대기</option>
          <option value="failed">실패</option>
          <option value="cancelled">취소됨</option>
          <option value="expired">기한 만료</option>
        </select>
      </Field>
      <Field label="분석 주제">
        <select value={params.get('topic') || ''} onChange={(e) => filter('topic', e.target.value)}>
          <option value="">전체 주제</option>
          {topics.map((name, i) => (
            <option key={topicId(i)} value={topicId(i)}>
              {name}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}
