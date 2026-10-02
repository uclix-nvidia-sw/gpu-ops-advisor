import { scheduleLabels, schedulePeriods, scheduleWindows } from '../lib/reportPeriod';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Field, Modal, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, DataView, More, QueryState } from '../components/live';
import { num, obj, queryPath, str, useCommand, useList, useResource, type Row } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
import { reportTitle } from '../lib/workflow';
import { ReportTimeNote, ReportScope } from '../components/ReportMeta';
import { reportTabs } from './Reports';
export function Schedules() {
  const { id } = useParams();
  return id ? <ScheduleDetail key={id} id={id} /> : <ScheduleList />;
}
function ScheduleList() {
  const app = useApp(),
    q = useList(app.ready ? queryPath('/schedules', { scope: app.scope, limit: 30 }) : null, true);
  return (
    <div className="page">
      <PageHead
        eyebrow="REPORT SCHEDULES"
        title="자동 보고서 설정"
        description="매일·매주·매월 지정한 시각에 보고서를 자동으로 만듭니다."
        actions={
          <Link className="button primary" to="/reports/new?schedule=true">
            자동 생성 설정
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <ReportTimeNote />
      <Panel title="등록된 일정">
        <QueryState query={q} empty={!q.items.length}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>일정</th>
                  <th>자동 생성</th>
                  <th>최근 실행</th>
                  <th>다음 실행 예정</th>
                  <th>실행 주기</th>
                </tr>
              </thead>
              <tbody>
                {q.items.map((s) => (
                  <tr key={str(s.id)}>
                    <td>
                      <Link className="text-link" to={`/schedules/${str(s.id)}`}>
                        {str(s.name, reportTitle(obj(s.report_spec)))}
                      </Link>
                      <ReportScope job={obj(s.report_spec)} />
                    </td>
                    <td>
                      <Badge
                        status={s.enabled ? 'available' : 'unknown'}
                        label={s.enabled ? '사용' : '일시 정지'}
                      />
                    </td>
                    <td className="schedule-execution-cell">
                      {s.awaiting_occurrence === true && (
                        <div className="schedule-overdue">
                          <Badge status="warning" label="예정 시각 지남 · 요청 기록 없음" />
                          <p className="cell-sub">
                            {formatDate(str(s.next_run_at))} 예정분의 요청이 아직 기록되지
                            않았습니다.
                          </p>
                        </div>
                      )}
                      {s.latest_occurrence ? (
                        <>
                          {s.awaiting_occurrence === true && (
                            <p className="cell-sub">마지막으로 기록된 회차</p>
                          )}
                          <ScheduleExecution occurrence={obj(s.latest_occurrence)} />
                        </>
                      ) : (
                        <Badge
                          status="unknown"
                          label={
                            s.latest_occurrence === null
                              ? '아직 실행 회차 없음'
                              : '실행 정보 미확인'
                          }
                        />
                      )}
                      <p className="cell-sub">
                        <Link className="text-link" to={`/schedules/${str(s.id)}#schedule-runs`}>
                          실행 내역 보기
                        </Link>
                      </p>
                    </td>
                    <td>{s.enabled ? formatDate(str(s.next_run_at)) : '일시 정지 중'}</td>
                    <td>
                      {scheduleLabels[str(s.frequency)] || '주기 미확인'}
                      {s.frequency === 'weekly' &&
                        ` ${['', '월', '화', '수', '목', '금', '토', '일'][num(s.weekday)] || '?'}요일`}
                      {s.frequency === 'monthly' && ` ${str(s.day, String(s.day ?? '?'))}일`}{' '}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
        <More query={q} />
      </Panel>
    </div>
  );
}
function ScheduleDetail({ id }: { id: string }) {
  const q = useResource(`/schedules/${id}`, undefined, true),
    occurrences = useList(`/schedules/${id}/occurrences?limit=30`, true),
    cmd = useCommand(),
    app = useApp();
  const [edit, setEdit] = useState(false);
  const s = q.data || {};
  return (
    <div className="page">
      <PageHead
        eyebrow="SCHEDULE DETAIL"
        title={str(s.name, reportTitle(obj(s.report_spec)))}
        description={id}
        actions={
          <Link className="button" to="/schedules">
            자동 보고서 설정 목록
          </Link>
        }
      />
      <ReportTimeNote />
      <QueryState query={q}>
        <Panel title="실행 조건">
          <div className="live-padding stack">
            <div className="head-actions">
              <Badge
                status={s.enabled ? 'available' : 'unknown'}
                label={s.enabled ? '사용' : '일시 정지'}
              />
              <span>
                다음 실행 예정: {s.enabled ? formatDate(str(s.next_run_at)) : '일시 정지 중'}
              </span>
              <span>revision {num(s.revision)}</span>
            </div>
            <DataView
              reportDisplay
              value={{ frequency: s.frequency, period: s.period, report_spec: s.report_spec }}
            />
            <details>
              <summary>원본 일정 설정</summary>
              <DataView value={{ local_time: s.local_time, timezone: s.timezone }} />
            </details>
            <div className="head-actions">
              <button
                className="button"
                disabled={cmd.busy || !app.canOperate}
                onClick={async () => {
                  if (
                    await cmd.run(
                      `/schedules/${id}`,
                      { enabled: !s.enabled },
                      { method: 'PATCH', version: num(s.version) },
                    )
                  )
                    app.notify('일정 상태를 저장했습니다.');
                }}
              >
                {s.enabled ? '일시 정지' : '다시 사용'}
              </button>
              <button className="button" onClick={() => setEdit(true)}>
                실행 조건 편집
              </button>
            </div>
            <CommandError error={cmd.error} />
          </div>
        </Panel>
        <section id="schedule-runs">
          <Panel title="실행 회차">
            <p className="live-padding">
              접수는 실행 완료가 아닙니다. 실제 시작·종료 기록을 확인하세요. 완료된 보고서도 분석
              근거가 부족할 수 있습니다.
            </p>
            <QueryState query={occurrences} empty={!occurrences.items.length}>
              <div className="live-padding stack">
                {occurrences.items.map((o) => (
                  <div className="data-item" key={str(o.id)}>
                    <ScheduleExecution occurrence={o} />
                    <p className="cell-sub">
                      분석 기간: {formatDate(str(o.period_start))} – {formatDate(str(o.period_end))}
                    </p>
                    <details>
                      <summary>회차 원본 기록</summary>
                      <DataView value={o} />
                    </details>
                    {app.mode === 'developer' && (
                      <details>
                        <summary>이 회차의 DB 키 연결 설명</summary>
                        <dl className="live-details">
                          <div>
                            <dt>일정 조건</dt>
                            <dd>
                              <code>
                                schedule_occurrences.(schedule_id, revision) →
                                schedule_revisions.(schedule_id, revision)
                              </code>
                              <p>
                                이 회차가 사용한 일정 버전입니다. 현재 일정의 revision으로 대체하지
                                않습니다.
                              </p>
                            </dd>
                          </div>
                          <div>
                            <dt>전달 기록</dt>
                            <dd>
                              <code>schedule_occurrences.outbox_id → enqueue_outbox.id</code>
                              <p>
                                Backend가 JC에 전달할 요청입니다. 원본 outbox 조회 API는 제공되지
                                않습니다.
                              </p>
                            </dd>
                          </div>
                          <div>
                            <dt>실행 작업</dt>
                            <dd>
                              <code>schedule_occurrences.job_id → jobs.id</code>
                              <p>
                                accepted는 JC 접수입니다. 작업 보기에서 실행 시도와 공개 결과를
                                확인하세요.
                              </p>
                            </dd>
                          </div>
                        </dl>
                      </details>
                    )}
                    <div className="head-actions">
                      {o.job_id != null && (
                        <Link
                          className="button"
                          to={`/jobs/${str(o.job_id)}`}
                          state={{ from: `/schedules/${id}` }}
                        >
                          작업 보기
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </QueryState>
            <More query={occurrences} />
          </Panel>
        </section>
      </QueryState>
      {edit && <ScheduleEditor initial={s} onClose={() => setEdit(false)} />}
    </div>
  );
}
const occurrenceReasons: Record<string, string> = {
  timeout: '시간 초과',
  outside_catchup_window: '자동 복구 가능한 기간을 지나 실행하지 않았습니다.',
  max_catchup_exceeded: '한 번에 복구할 수 있는 회차 수를 초과했습니다.',
  already_reserved_period: '같은 분석 기간의 요청이 이미 있어 중복 실행하지 않았습니다.',
  dispatch_deadline_exceeded: '작업 전달 기한이 지났습니다.',
};

export function ScheduleExecution({ occurrence }: { occurrence: Row }) {
  const job = obj(occurrence.execution);
  const state = str(job.status);
  const started = Boolean(job.started_at) || num(job.attempt_no) > 0;
  const status =
    state ||
    (occurrence.status === 'failed'
      ? 'failed'
      : occurrence.status === 'missed'
        ? 'warning'
        : 'unknown');
  const label = state
    ? state === 'queued'
      ? '접수됨 · 실행 대기'
      : state === 'expired' && !started
        ? '실행 전 기한 만료'
        : labels[state] || '실행 상태 미확인'
    : {
        pending: '요청 전달 확인 중',
        accepted: '접수됨 · 실행 상태 미확인',
        missed: '실행 건너뜀',
        failed: '요청 전달 실패',
      }[str(occurrence.status)] || '실행 상태 미확인';
  const reason = str(job.attempt_reason, str(job.termination_reason, str(occurrence.reason)));
  return (
    <div className="schedule-execution">
      <Badge status={status} label={label} />
      <p className="cell-sub">예정 {formatDate(str(occurrence.scheduled_for))}</p>
      {job.started_at ? (
        <p className="cell-sub">
          {num(job.attempt_no)}차 시작 {formatDate(str(job.started_at))}
        </p>
      ) : (
        <p className="cell-sub">
          {started
            ? '시작 시각 미확인'
            : state && num(job.attempt_no) === 0
              ? '아직 실행 시작 기록 없음'
              : '실제 실행은 작업 기록에서 확인합니다.'}
        </p>
      )}
      {job.ended_at != null && (
        <p className="cell-sub">시도 종료 {formatDate(str(job.ended_at))}</p>
      )}
      {reason && (
        <p className="cell-sub">사유: {occurrenceReasons[reason] || labels[reason] || reason}</p>
      )}
      {job.queue_reason != null && (
        <p className="cell-sub">{labels[str(job.queue_reason)] || str(job.queue_reason)}</p>
      )}
      {state === 'succeeded' && job.result_ref != null && occurrence.job_id != null && (
        <Link className="text-link" to={`/reports/${str(occurrence.job_id)}#final-report`}>
          보고서 보기
        </Link>
      )}
    </div>
  );
}

function ScheduleEditor({ initial, onClose }: { initial: Row; onClose: () => void }) {
  const cmd = useCommand(),
    calendar = initial;
  const [frequency, setFrequency] = useState(str(calendar.frequency, 'daily')),
    [time, setTime] = useState(str(calendar.local_time, '09:00')),
    [day, setDay] = useState(num(calendar.day, 1)),
    [weekday, setWeekday] = useState(num(calendar.weekday, 1));
  return (
    <Modal title="일정 실행 조건 편집" onClose={onClose}>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await cmd.run(
              `/schedules/${str(initial.id)}`,
              {
                frequency,
                local_time: time,
                timezone: str(calendar.timezone, 'Asia/Seoul'),
                period: schedulePeriods[frequency],
                ...(frequency === 'weekly' ? { weekday } : frequency === 'monthly' ? { day } : {}),
              },
              { method: 'PATCH', version: num(initial.version) },
            )
          )
            onClose();
        }}
      >
        <Field label="반복 주기">
          <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            {Object.entries(scheduleLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label={
            calendar.timezone && calendar.timezone !== 'Asia/Seoul'
              ? `원본 실행 시각 · ${str(calendar.timezone)}`
              : '실행 시각'
          }
        >
          <input required type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </Field>
        {frequency === 'weekly' && (
          <Field label="요일 (월요일 1 ~ 일요일 7)">
            <input
              required
              type="number"
              min={1}
              max={7}
              value={weekday}
              onChange={(e) => setWeekday(+e.target.value)}
            />
          </Field>
        )}
        {frequency === 'monthly' && (
          <Field label="일">
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
        <Notice>
          {scheduleWindows[frequency]} 전체를 분석합니다. 저장된 새 revision은 이후 회차에
          적용됩니다.
        </Notice>
        <CommandError error={cmd.error} />
        <button className="button primary" disabled={cmd.busy}>
          조건 저장
        </button>
      </form>
    </Modal>
  );
}
