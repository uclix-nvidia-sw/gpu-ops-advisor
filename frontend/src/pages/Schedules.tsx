import { ArrowLeft, ArrowUpRight, Pause, Play, Plus } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Empty, Field, Modal, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { reportId, topicId, topics } from '../data/fixtures';
import { formatDate, inScope, labels, nextSchedule, scopeLabel } from '../lib/domain';
import { useApp, useDatabase } from '../lib/store';
import { reportTabs } from './Reports';
export function Schedules() {
  const { id } = useParams();
  const { db, mutate } = useDatabase();
  const app = useApp();
  const item = db?.schedules.find((s) => s.id === id);
  const [modal, setModal] = useState('');
  const [name, setName] = useState('');
  const [frequency, setFrequency] = useState('daily');
  const [time, setTime] = useState('09:00');
  const [weekday, setWeekday] = useState(1);
  const [day, setDay] = useState(1);
  const [chosen, setChosen] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [version, setVersion] = useState(0);
  const [error, setError] = useState('');
  if (!db) return <div className="loading">일정 조회 중…</div>;
  if (id && !item) return <Empty title="없거나 접근할 수 없는 항목" />;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (!reason.trim()) throw new Error('변경 사유를 입력해 주세요.');
      if (!chosen.length) throw new Error('하나 이상의 분석 주제를 선택해 주세요.');
      await mutate((d) => {
        const s = d.schedules.find((s) => s.id === id)!;
        if (s.revision !== version)
          throw new Error('일정 버전이 변경되었습니다. 최신본을 확인해 주세요.');
        if (modal === 'toggle') s.enabled = !s.enabled;
        else
          Object.assign(s, { name, frequency, local_time: time, weekday, day, topic_ids: chosen });
        s.revision++;
        s.reason = reason;
        s.next_run = nextSchedule(s.frequency, s.local_time, s.weekday, s.day);
      });
      setModal('');
      app.notify('일정 변경이 저장되었습니다. 다음 발생부터 새 revision이 적용됩니다.');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const open = (mode: string) => {
    setModal(mode);
    setName(item!.name);
    setFrequency(item!.frequency);
    setTime(item!.local_time);
    setDay(item!.day);
    setWeekday(item!.weekday);
    setChosen(item!.topic_ids);
    setVersion(item!.revision);
    setReason('');
    setError('');
  };
  return (
    <div className="page">
      {item && (
        <Link className="back-link" to="/schedules">
          <ArrowLeft size={15} />
          정기 일정
        </Link>
      )}
      <PageHead
        eyebrow="SCHEDULED REPORTS"
        title={item ? item.name : '정기 일정'}
        description={
          item
            ? '일정의 조건과 적용 revision, 발생 이력을 확인합니다.'
            : '일·주·월 단위로 운영 보고서를 준비하는 일정을 관리합니다.'
        }
        actions={
          item ? (
            app.role === 'operator' && (
              <>
                <button className="button" onClick={() => open('toggle')}>
                  {item.enabled ? <Pause size={15} /> : <Play size={15} />}
                  {item.enabled ? '일시중지' : '재개'}
                </button>
                <button className="button primary" onClick={() => open('edit')}>
                  일정 수정
                </button>
              </>
            )
          ) : (
            <Link className="button primary" to="/reports/new">
              <Plus size={16} />새 정기 일정
            </Link>
          )
        }
      />
      {!item && <NavTabs items={reportTabs} />}
      <Notice>
        프론트엔드 데모에서는 일정 조건만 저장합니다. 실제 예약 실행·발생 원장·권한 재검사는 백엔드
        연결 후 동작합니다.
      </Notice>
      {item ? (
        <>
          <div className="two-column">
            <Panel title="일정 조건">
              <div className="panel-body">
                <dl className="details">
                  <dt>상태</dt>
                  <dd>
                    <Badge
                      status={item.enabled ? 'ready' : 'neutral'}
                      label={item.enabled ? '활성' : '일시중지'}
                    />
                  </dd>
                  <dt>반복</dt>
                  <dd>
                    {labels[item.frequency]} {item.local_time} KST
                    {item.frequency === 'weekly'
                      ? ` · ${['일', '월', '화', '수', '목', '금', '토'][item.weekday]}요일`
                      : item.frequency === 'monthly'
                        ? ` · ${item.day}일 (없는 날짜는 말일)`
                        : ''}
                  </dd>
                  <dt>시간대</dt>
                  <dd>{item.timezone}</dd>
                  <dt>분석 기간</dt>
                  <dd>
                    {item.frequency === 'daily'
                      ? '직전 완료 일'
                      : item.frequency === 'weekly'
                        ? '직전 완료 주 · 월~월'
                        : '직전 완료 월'}
                  </dd>
                  <dt>저장 범위</dt>
                  <dd>{scopeLabel(item.scope)}</dd>
                  <dt>분석 주제</dt>
                  <dd>{item.topic_ids.join(' · ')}</dd>
                  <dt>집계 단위</dt>
                  <dd>{String(item.report_conditions?.group_by || 'cluster')}</dd>
                </dl>
              </div>
            </Panel>
            <Panel title="적용·실행 정보">
              <div className="panel-body">
                <dl className="details">
                  <dt>현재 revision</dt>
                  <dd>v{item.revision}</dd>
                  <dt>변경 적용</dt>
                  <dd>변경 후 다음 발생분부터</dd>
                  <dt>다음 예정</dt>
                  <dd>
                    {item.enabled
                      ? `${formatDate(item.next_run)} KST`
                      : '일시중지 · 재개 시 다시 계산'}
                  </dd>
                  <dt>소유자</dt>
                  <dd>김운영</dd>
                  <dt>최근 변경 사유</dt>
                  <dd>{item.reason || '최초 생성'}</dd>
                </dl>
              </div>
            </Panel>
          </div>
          <Panel
            title="발생 이력"
            description="이미 접수한 발생분의 범위·기간은 일정 변경으로 덮어쓰지 않습니다."
          >
            {item.id === '0464241e-f6ed-4186-8e35-5ad1140e0700' ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>예정 시각</th>
                      <th>revision</th>
                      <th>발생 상태</th>
                      <th>사유 / 연결 결과</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>09.16 09:00 KST</td>
                      <td>v1</td>
                      <td>
                        <Badge status="ready" label="accepted" />
                      </td>
                      <td>
                        <Link className="text-link" to={`/reports/${reportId}`}>
                          예시 보고서
                          <ArrowUpRight size={14} />
                        </Link>
                      </td>
                    </tr>
                    <tr>
                      <td>09.15 09:00 KST</td>
                      <td>v1</td>
                      <td>
                        <Badge status="blocked" label="blocked" />
                      </td>
                      <td>예시 · 요청 범위 권한 재검사 필요</td>
                    </tr>
                    <tr>
                      <td>09.14 09:00 KST</td>
                      <td>v1</td>
                      <td>
                        <Badge status="warning" label="missed" />
                      </td>
                      <td>예시 · 스케줄러 중단으로 미접수</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="발생 이력이 없습니다."
                description="이 일정은 데모에서 생성되었습니다. 예약 실행은 백엔드 통합 대상입니다."
              />
            )}
          </Panel>
        </>
      ) : (
        <Panel>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>일정 이름</th>
                  <th>반복</th>
                  <th>대상</th>
                  <th>상태</th>
                  <th>다음 예정 (KST)</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {db.schedules
                  .filter((s) => s.scope.clusters.some((c) => inScope(app.scope, c.cluster_id)))
                  .map((s) => (
                    <tr key={s.id}>
                      <td>
                        <Link to={`/schedules/${s.id}`}>
                          <b>{s.name}</b>
                          <small>revision {s.revision}</small>
                        </Link>
                      </td>
                      <td>
                        {labels[s.frequency]} {s.local_time}
                      </td>
                      <td>{scopeLabel(s.scope)}</td>
                      <td>
                        <Badge
                          status={s.enabled ? 'ready' : 'neutral'}
                          label={s.enabled ? '활성' : '일시중지'}
                        />
                      </td>
                      <td>{s.enabled ? formatDate(s.next_run) : '—'}</td>
                      <td>
                        <Link className="text-link" to={`/schedules/${s.id}`}>
                          상세
                          <ArrowUpRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {modal && (
        <Modal
          title={
            modal === 'edit' ? '일정 조건 수정' : item!.enabled ? '일정 일시중지' : '일정 재개'
          }
          onClose={() => setModal('')}
        >
          <form className="stack" onSubmit={save}>
            {modal === 'edit' && (
              <>
                <Field label="일정 이름">
                  <input required value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <div className="form-grid">
                  <Field label="주기">
                    <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                      <option value="daily">매일</option>
                      <option value="weekly">매주</option>
                      <option value="monthly">매월</option>
                    </select>
                  </Field>
                  <Field label="실행 시각">
                    <input
                      required
                      type="time"
                      value={time}
                      onChange={(e) => setTime(e.target.value)}
                    />
                  </Field>
                  {frequency === 'weekly' && (
                    <Field label="요일">
                      <select value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
                        {['일', '월', '화', '수', '목', '금', '토'].map((d, i) => (
                          <option value={i} key={i}>
                            {d}
                          </option>
                        ))}
                      </select>
                    </Field>
                  )}
                  {frequency === 'monthly' && (
                    <Field label="날짜">
                      <input
                        type="number"
                        required
                        min="1"
                        max="31"
                        value={day}
                        onChange={(e) => setDay(Number(e.target.value))}
                      />
                    </Field>
                  )}
                </div>
                <div className="compact-checks">
                  {topics.map((t, i) => (
                    <label className="check" key={t}>
                      <input
                        type="checkbox"
                        checked={chosen.includes(topicId(i))}
                        onChange={(e) =>
                          setChosen((s) =>
                            e.target.checked
                              ? [...s, topicId(i)]
                              : s.filter((x) => x !== topicId(i)),
                          )
                        }
                      />
                      {t}
                    </label>
                  ))}
                </div>
              </>
            )}
            <Notice>진행 중인 작업과 이미 접수된 기간은 변경하지 않습니다.</Notice>
            <Field label="변경 사유 *">
              <textarea required value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary">변경 저장</button>
          </form>
        </Modal>
      )}
    </div>
  );
}
