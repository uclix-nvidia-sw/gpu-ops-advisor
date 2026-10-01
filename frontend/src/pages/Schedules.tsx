import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Field, Modal, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, DataView, More, QueryState } from '../components/live';
import { num, obj, queryPath, str, useCommand, useList, useResource, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';
import { useApp } from '../lib/store';
import { reportScope, reportTitle } from '../lib/workflow';
import { reportTabs } from './Reports';
export function Schedules() {
  const { id } = useParams();
  return id ? <ScheduleDetail key={id} id={id} /> : <ScheduleList />;
}
function ScheduleList() {
  const app = useApp(),
    q = useList(app.ready ? queryPath('/schedules', { scope: app.scope, limit: 30 }) : null);
  return (
    <div className="page">
      <PageHead
        eyebrow="REPORT SCHEDULES"
        title="정기 일정"
        description="보고서를 자동 생성할 주기와 다음 실행 시각을 확인합니다."
        actions={
          <Link className="button primary" to="/reports/new?schedule=true">
            정기 일정 등록
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <Panel title="등록된 일정">
        <QueryState query={q} empty={!q.items.length}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>일정</th>
                  <th>상태</th>
                  <th>다음 실행 (KST)</th>
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
                      <p className="cell-sub">{reportScope(obj(s.report_spec))}</p>
                    </td>
                    <td>
                      <Badge
                        status={s.enabled ? 'available' : 'unknown'}
                        label={s.enabled ? '사용' : '일시 정지'}
                      />
                    </td>
                    <td>{formatDate(str(s.next_run_at))}</td>
                    <td>
                      {(
                        { daily: '매일', weekly: '매주', monthly: '매월' } as Record<string, string>
                      )[str(s.frequency)] || '주기 미확인'}
                      {s.frequency === 'weekly' &&
                        ` ${['', '월', '화', '수', '목', '금', '토', '일'][num(s.weekday)] || '?'}요일`}
                      {s.frequency === 'monthly' && ` ${str(s.day, String(s.day ?? '?'))}일`}{' '}
                      {str(s.local_time)} · {str(s.timezone, '시간대 미확인')}
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
  const q = useResource(`/schedules/${id}`),
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
            일정 목록
          </Link>
        }
      />
      <QueryState query={q}>
        <Panel title="실행 조건">
          <div className="live-padding stack">
            <div className="head-actions">
              <Badge
                status={s.enabled ? 'available' : 'unknown'}
                label={s.enabled ? '사용' : '일시 정지'}
              />
              <span>다음 실행: {formatDate(str(s.next_run_at))}</span>
              <span>revision {num(s.revision)}</span>
            </div>
            <DataView
              value={{
                frequency: s.frequency,
                local_time: s.local_time,
                timezone: s.timezone,
                period: s.period,
                report_spec: s.report_spec,
              }}
            />
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
        <Panel title="실행 회차">
          <QueryState query={occurrences} empty={!occurrences.items.length}>
            <div className="live-padding stack">
              {occurrences.items.map((o) => (
                <div className="data-item" key={str(o.id)}>
                  <strong>{formatDate(str(o.scheduled_for))} 예정 회차</strong>
                  <DataView value={o} />
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
      </QueryState>
      {edit && <ScheduleEditor initial={s} onClose={() => setEdit(false)} />}
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
                period: (
                  {
                    daily: 'previous_complete_day',
                    weekly: 'previous_complete_week',
                    monthly: 'previous_complete_month',
                  } as Record<string, string>
                )[frequency],
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
            <option value="daily">매일</option>
            <option value="weekly">매주</option>
            <option value="monthly">매월</option>
          </select>
        </Field>
        <Field label="실행 시각">
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
        <Notice>저장된 새 revision은 이후 회차에 적용됩니다.</Notice>
        <CommandError error={cmd.error} />
        <button className="button primary" disabled={cmd.busy}>
          조건 저장
        </button>
      </form>
    </Modal>
  );
}
