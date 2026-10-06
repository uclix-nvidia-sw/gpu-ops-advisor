import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Field, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, JobRows, More, QueryState } from '../components/live';
import { queryPath, str, topicId, topics, useCommand, useList } from '../lib/live';
import { scopeLabel } from '../lib/domain';
import { reportKind, reportKinds, reportSelection, topicDisplayBases } from '../lib/reportKinds';
import { useReportListPosition } from '../lib/reportNavigation';
import {
  previousReportDay,
  reportDayRange,
  reportDaySummary,
  scheduleLabels,
  schedulePeriods,
  scheduleWindows,
} from '../lib/reportPeriod';
import { ReportTimeNote } from '../components/ReportMeta';
import { useApp } from '../lib/store';
export const reportTabs = [
  { to: '/reports', label: '보고서 이력' },
  { to: '/schedules', label: '자동 보고서 설정' },
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
    <div className="page report-workspace">
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
      <ReportTimeNote />
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
  const [selectedIds, setSelectedIds] = useState<string[]>(
      params.has('kind') ? [reportKind(params.get('kind')).id] : reportKinds.map((kind) => kind.id),
    ),
    [enableComparison, setEnableComparison] = useState(false),
    [scheduled, setScheduled] = useState(params.get('schedule') === 'true'),
    [frequency, setFrequency] = useState('daily'),
    [localTime, setLocalTime] = useState('09:00'),
    [weekday, setWeekday] = useState(1),
    [day, setDay] = useState(1),
    [start, setStart] = useState(previousReportDay()),
    [end, setEnd] = useState(previousReportDay()),
    [compareStart, setCompareStart] = useState(''),
    [compareEnd, setCompareEnd] = useState('');
  const [actionRefs, setActionRefs] = useState(''),
    [resourceName, setResourceName] = useState(''),
    [resourceUnit, setResourceUnit] = useState(''),
    [resourceCluster, setResourceCluster] = useState(app.scope.clusters[0]?.cluster_id || '');
  const selectedKinds = reportKinds.filter((kind) => selectedIds.includes(kind.id));
  const selection = reportSelection(selectedIds);
  const comprehensive = selectedKinds.length === reportKinds.length;
  const hasComparison = selectedIds.includes('comparison');
  const compare = hasComparison && enableComparison && !scheduled;
  const waiting = selectedIds.includes('waiting');
  const chooseKind = (id: string) => {
    setSelectedIds(
      selectedIds.includes(id)
        ? selectedIds.filter((selected) => selected !== id)
        : [...selectedIds, id],
    );
    if (id === 'comparison') {
      setEnableComparison(false);
      setActionRefs('');
      setCompareStart('');
      setCompareEnd('');
    }
    if (id === 'waiting') {
      setResourceName('');
      setResourceUnit('');
    }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (!selection.topic_ids.length) throw new Error('보고서 종류를 하나 이상 선택하세요.');
      if (compare && !actionRefs.trim()) {
        throw new Error(
          '조치 전후 비교는 수행한 조치 기록 ID와 비교 기간을 입력해 직접 요청하세요.',
        );
      }
      const template = {
        scope: app.scope,
        ...selection,
        ...(compare && actionRefs.trim()
          ? {
              action_record_ids: actionRefs
                .split('\n')
                .map((v) => v.trim())
                .filter(Boolean),
            }
          : {}),
        ...(waiting && resourceName.trim()
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
    <div className="page report-workspace">
      <PageHead
        eyebrow="NEW REPORT"
        title="새 운영 보고서"
        description="전체 종합 또는 필요한 종류를 여러 개 선택해 보고서 한 장으로 확인하세요."
      />
      <NavTabs items={reportTabs} />
      <ReportTimeNote />
      <form className="stack" onSubmit={submit}>
        <fieldset className="report-kind-fieldset">
          <legend>어떤 보고서를 만들까요?</legend>
          <div className="report-mode-options">
            <label className="check">
              <input
                type="radio"
                name="report-mode"
                checked={comprehensive}
                onChange={() => setSelectedIds(reportKinds.map((kind) => kind.id))}
              />
              전체 종합보고서 · 모든 소주제
            </label>
            <label className="check">
              <input
                type="radio"
                name="report-mode"
                checked={!comprehensive}
                onChange={() => {
                  setSelectedIds(['namespace']);
                  setEnableComparison(false);
                  setActionRefs('');
                  setCompareStart('');
                  setCompareEnd('');
                  setResourceName('');
                  setResourceUnit('');
                }}
              />
              직접 선택 · 여러 종류 선택 가능
            </label>
          </div>
          <p className="report-selection-summary">
            선택한 {selectedKinds.length}개 종류 · {selection.topic_ids.length}개 분석 주제를 보고서
            한 장에 담습니다.
            <br />
            카드의 체크를 바꾸면 직접 선택으로 전환됩니다.
          </p>
          <div className="report-kind-grid">
            {reportKinds.map((item) => (
              <label
                key={item.id}
                className={`report-kind-card${selectedIds.includes(item.id) ? ' selected' : ''}`}
              >
                <input
                  type="checkbox"
                  name="report-kind"
                  value={item.id}
                  checked={selectedIds.includes(item.id)}
                  onChange={() => chooseKind(item.id)}
                />
                <span>
                  <strong>{item.name}</strong>
                  <span className="report-kind-description">{item.description}</span>
                  <small>포함 주제 · {item.topicIds.join(' · ')}</small>
                  <span className="report-kind-basis">
                    표시 기준
                    <br />
                    {item.topicIds.map((id) => (
                      <span key={id}>
                        {id} · {topicDisplayBases[id]}
                      </span>
                    ))}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <section className="report-kind-detail" aria-label="선택한 보고서 안내" aria-live="polite">
          <h2>{comprehensive ? '전체 종합보고서' : '선택한 소주제 안내'}</h2>
          {!selectedKinds.length && <Notice>보고서 종류를 하나 이상 선택하세요.</Notice>}
          <p>
            각 소주제는 자신의 계산 기준을 사용합니다. 자료가 부족한 소주제도 숨기지 않고 이유를
            표시합니다.
          </p>
          {selectedKinds.map((kind) => (
            <details key={kind.id}>
              <summary>{kind.name} · 필요한 자료와 해석</summary>
              <p>{kind.insight}</p>
              <p>
                <strong>필요한 자료:</strong> {kind.requirement}
              </p>
              <p>{kind.limit}</p>
            </details>
          ))}
          <p className="cell-sub">
            자료 보유 여부는 실행 후 확인됩니다. 전체 선택은 수집량과 실행시간이 늘어날 수 있습니다.
          </p>
          <Link className="text-link" to="/operator-guide#guide-topics">
            보고서 종류와 세부 분석 안내
          </Link>
        </section>
        {hasComparison && (
          <Notice>
            <strong>운영 조치 전후 비교</strong>
            <p>
              {scheduled
                ? '자동보고서는 비교 조건을 임의로 만들지 않습니다. 해당 소주제에 조치 기록·비교 기간 미지정 사유를 표시합니다.'
                : '비교 조건을 넣지 않아도 요청할 수 있습니다. 해당 소주제에 미실행 이유를 표시하고 다른 분석은 진행합니다.'}
            </p>
            {!scheduled && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={enableComparison}
                  onChange={(e) => setEnableComparison(e.target.checked)}
                />
                조치 기록과 비교 기간 입력
              </label>
            )}
          </Notice>
        )}
        {compare && (
          <Panel title="비교할 운영 조치">
            <div className="live-padding">
              <Field
                label="수행한 조치 기록 ID"
                hint="서버에 수행됨으로 기록된 조치 ID를 한 줄에 하나씩 입력하세요."
              >
                <textarea
                  required
                  rows={2}
                  value={actionRefs}
                  onChange={(e) => setActionRefs(e.target.value)}
                />
              </Field>
            </div>
          </Panel>
        )}
        {waiting && (
          <details>
            <summary>자원 조건 지정 (선택)</summary>
            <div className="form-grid">
              <Field label="자원 클러스터">
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
          </details>
        )}
        <Panel title="범위와 실행 조건">
          <div className="live-padding stack">
            <Notice>{scopeLabel(app.scope)}</Notice>
            <label className="check">
              <input
                type="checkbox"
                checked={scheduled}
                onChange={(e) => setScheduled(e.target.checked)}
              />
              자동 생성 설정
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
                  <Field label="실행 시각">
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
                  <Field label="분석 시작일">
                    <input
                      required
                      type="date"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </Field>
                  <Field label="분석 종료일 (포함)">
                    <input
                      required
                      type="date"
                      min={start}
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </Field>
                </div>
                {compare && (
                  <div className="form-grid" role="group" aria-label="조치 이전 비교 기간">
                    <Field label="비교 시작일">
                      <input
                        required
                        type="date"
                        value={compareStart}
                        onChange={(e) => setCompareStart(e.target.value)}
                      />
                    </Field>
                    <Field label="비교 종료일 (포함)">
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
          {!scheduled && (
            <p>기본값은 어제 하루입니다. 요청 시점부터 거슬러 올라간 최근 24시간이 아닙니다.</p>
          )}
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
            disabled={cmd.busy || !app.canOperate || !selection.topic_ids.length}
          >
            {cmd.busy ? '접수 확인 중…' : scheduled ? '자동 생성 설정 저장' : '보고서 요청'}
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
