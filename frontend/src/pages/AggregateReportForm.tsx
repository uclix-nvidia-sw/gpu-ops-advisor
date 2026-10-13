import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { PageHead, Panel, Notice } from '../components/ui';
import { CommandError } from '../components/live';
import { ReportPeriod } from '../components/ReportMeta';
import { useApp } from '../lib/store';
import { useCommand, str } from '../lib/live';
import { previousReportDay, reportDayRange, schedulePeriods } from '../lib/reportPeriod';
import '../components/aggregate-report.css';

export function aggregatePeriod(last: string, frequency: string) {
  const first = new Date(`${last}T00:00:00Z`);
  if (frequency === 'weekly') first.setUTCDate(first.getUTCDate() - 6);
  return reportDayRange(first.toISOString().slice(0, 10), last);
}

export function AggregateReportForm() {
  const app = useApp(),
    command = useCommand(),
    navigate = useNavigate();
  const [params] = useSearchParams();
  const [scheduled, setScheduled] = useState(params.get('schedule') === 'true');
  const [frequency, setFrequency] = useState('daily');
  const [lastDay, setLastDay] = useState(previousReportDay());
  const [time, setTime] = useState('09:00');
  const [weekday, setWeekday] = useState('1');
  let period;
  try {
    period = aggregatePeriod(lastDay, frequency);
  } catch {
    period = undefined;
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const spec = {
        scope: app.scope,
        topic_ids: ['namespace_usage', 'incident_summary'],
        group_by: ['cluster', 'namespace'],
      };
      const body = scheduled
        ? {
            enabled: true,
            report_spec: spec,
            frequency,
            local_time: time,
            timezone: 'Asia/Seoul',
            period: schedulePeriods[frequency],
            ...(frequency === 'weekly' ? { weekday: Number(weekday) } : {}),
          }
        : {
            ...spec,
            timezone: 'Asia/Seoul',
            time_range: aggregatePeriod(lastDay, frequency),
            ...(params.get('parent_job_id') ? { parent_job_id: params.get('parent_job_id') } : {}),
          };
      const response = await command.run(scheduled ? '/schedules' : '/reports', body, {
        idempotent: true,
      });
      if (response)
        navigate(
          scheduled
            ? `/schedules/${str(response.id, str(response.schedule_id))}`
            : `/reports/${str(response.job_id)}`,
        );
    } catch (error) {
      command.setError(error instanceof Error ? error.message : '요청 조건을 확인해 주세요.');
    }
  };
  return (
    <div className="page aggregate-form">
      <PageHead
        eyebrow=""
        title="운영 보고서 만들기"
        description="Namespace별 GPU 활동과 기간 내 사건을 이전 기간과 비교합니다."
      />
      <form onSubmit={submit}>
        <Panel
          title="분석 범위와 기간"
          description="상단에서 선택한 클러스터·Namespace 범위로 분석합니다."
        >
          <div className="aggregate-fields">
            <label>
              생성 방식
              <select
                value={scheduled ? 'scheduled' : 'manual'}
                onChange={(e) => setScheduled(e.target.value === 'scheduled')}
              >
                <option value="manual">직접 요청</option>
                <option value="scheduled">자동 보고서</option>
              </select>
            </label>
            <label>
              분석 기간
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                <option value="daily">일일 · 하루</option>
                <option value="weekly">주간 · 7일</option>
              </select>
            </label>
            {!scheduled && (
              <label>
                마지막 분석 날짜
                <input
                  type="date"
                  required
                  max={previousReportDay()}
                  value={lastDay}
                  onChange={(e) => setLastDay(e.target.value)}
                />
              </label>
            )}
            {scheduled && (
              <label>
                실행 시각 · 한국 시간
                <input
                  type="time"
                  required
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                />
              </label>
            )}
            {scheduled && frequency === 'weekly' && (
              <label>
                실행 요일
                <select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
                  {['월', '화', '수', '목', '금', '토', '일'].map((day, i) => (
                    <option key={day} value={i + 1}>
                      {day}요일
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="live-padding">
            {scheduled ? (
              <p>
                {frequency === 'daily' ? '직전 완료된 하루' : '직전 완료된 월요일~일요일'}를
                분석합니다. 기존 일정은 자동 변경되지 않습니다.
              </p>
            ) : (
              period && <ReportPeriod value={period} />
            )}
            <p>이전 기간 비교는 같은 범위의 직전 하루 또는 직전 7일을 함께 조회합니다.</p>
          </div>
        </Panel>
        <Panel title="보고서에 포함되는 내용">
          <div className="live-padding">
            <h3>Namespace 활동과 변화</h3>
            <p>비교표 · 시간대별 그래프 · 낮은 활동 시간대 · 이전 기간 대비 변화</p>
            <h3>사건과 반복 현황</h3>
            <p>기간 내 사건 · 동일 장비·증상의 반복 비교 · 기존 RCA 확인</p>
          </div>
        </Panel>
        <Notice>
          자료가 부족한 시간대는 0%로 표시하지 않습니다. 운영정책 대비 효율·GPU 회수 권고·새로운
          장애 원인 분석은 포함하지 않습니다.
        </Notice>
        <CommandError error={command.error} />
        <div className="aggregate-actions">
          <button
            className="button primary"
            type="submit"
            disabled={!app.canOperate || command.busy}
          >
            {scheduled ? '자동 보고서 등록' : '보고서 생성 요청'}
          </button>
          <Link to="/reports">목록으로</Link>
        </div>
      </form>
      <details>
        <summary>이전 분석 방식</summary>
        <p>기존 주제별 분석과 과거 보고서는 이전 계산 기준을 유지합니다.</p>
        <Link to="/reports/new?legacy=true">이전 주제별 보고서 요청</Link>
      </details>
    </div>
  );
}
