import { useState } from 'react';
import { obj, rows, str, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';
import { memoryPercent } from './NamespaceCharts';

const percentage = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100;
const hourKey = (h: Row) => `${Date.parse(str(h.start))}/${Date.parse(str(h.end))}`;
const label = (r: Row) => `${r.cluster_id} / ${r.namespace} · ${str(r.gpu_model) || '모델 미확인'}`;
const time = (s: unknown) => reportRequestTime(str(s));

// Read saved, complete hour bins only; never fill gaps or join mismatched periods.
export function operationalEvidence(value: Row) {
  const usage = rows(value.topics).find((t) => t.topic_id === 'namespace_usage');
  const narrative = rows(value.narrative).find((s) => s.topic_id === 'namespace_usage');
  const criteria = obj(obj(narrative?.selection).criteria);
  const low = criteria.low_activity_percent,
    high = criteria.high_memory_percent,
    highActivity = criteria.high_activity_percent;
  const start = Date.parse(str(obj(value.time_range).start));
  const end = Date.parse(str(obj(value.time_range).end));
  const validHour = (h: Row) => {
    const a = Date.parse(str(h.start)),
      b = Date.parse(str(h.end));
    return (
      a >= start &&
      b <= end &&
      b - a === 3600000 &&
      typeof h.sample_count === 'number' &&
      Number.isFinite(h.sample_count) &&
      h.sample_count > 0
    );
  };
  return rows(usage?.rows)
    .filter((r) => str(r.namespace))
    .map((r) => {
      const raw = rows(r.hours);
      const hours = raw.filter(
        (h) =>
          validHour(h) &&
          percentage(h.activity_percent) &&
          raw.filter(
            (other) =>
              Date.parse(str(other.start)) < Date.parse(str(h.end)) &&
              Date.parse(str(other.end)) > Date.parse(str(h.start)),
          ).length === 1,
      );
      const memory = rows(obj(r.gpu_memory).hours);
      const paired = hours.flatMap((h) => {
        const matches = memory.filter((m) => hourKey(m) === hourKey(h));
        const m = matches.length === 1 && validHour(matches[0]) ? memoryPercent(matches[0]) : null;
        return m === null ? [] : [{ hour: h, memory: m }];
      });
      const overlap =
        percentage(low) && percentage(high)
          ? paired.filter((p) => Number(p.hour.activity_percent) < low && p.memory >= high)
          : [];
      const peak = [...hours].sort(
        (a, b) => Number(b.activity_percent) - Number(a.activity_percent),
      )[0];
      return {
        row: r,
        key: JSON.stringify([r.cluster_id, r.namespace, r.gpu_model]),
        hours,
        paired,
        overlap,
        peak,
        low,
        high,
        highActivity,
      };
    });
}

export function OperationalInsights({ value }: { value: Row }) {
  const evidence = operationalEvidence(value);
  if (!evidence.length) return null;
  const resident = [...evidence]
    .filter((r) => r.overlap.length > 0)
    .sort((a, b) => b.overlap.length - a.overlap.length)[0];
  const burst = [...evidence]
    .filter(
      (r) =>
        r.peak &&
        percentage(r.row.activity_percent) &&
        percentage(r.highActivity) &&
        Number(r.peak.activity_percent) >= r.highActivity &&
        r.row.activity_percent < r.highActivity,
    )
    .sort((a, b) => Number(b.peak.activity_percent) - Number(a.peak.activity_percent))[0];
  return (
    <section id="c2-ops-insights" className="c2-ops-insights" aria-label="수치로 확인한 관측">
      <header>
        <h2>수치로 확인한 관측</h2>
        <span>저장된 수치·선별 기준으로 표시 · AI 해석은 아래 운영 제안에서 확인</span>
      </header>
      <div className="c2-coverage-strip">
        {[...new Set(evidence.map((e) => str(e.row.cluster_id)))].map((cluster) => {
          const records = evidence.filter((e) => e.row.cluster_id === cluster);
          const measured = records.filter((e) => percentage(e.row.activity_percent));
          return (
            <a href="#c2-observation-coverage" key={cluster}>
              <b>{cluster}</b>
              <span>
                활동률 확인 {measured.length}/{records.length}개 모델 기록
              </span>
              <strong>
                {measured.length === records.length ? '시간대 범위 확인' : '일부 판단 보류'}
              </strong>
            </a>
          );
        })}
      </div>
      <div className="c2-insight-list">
        {resident && (
          <article>
            <span className="c2-insight-kind">낮은 활동·높은 메모리의 동시 관측</span>
            <h3>{label(resident.row)}</h3>
            <p>
              같은 시간대의 활동률 {String(resident.low)}% 미만·메모리 {String(resident.high)}%
              이상이 <b>{resident.overlap.length}개 시간대</b>에서 함께 관측됐습니다.
            </p>
            <details>
              <summary>조건에 따른 참고 안내 · AI 해석 아님</summary>
              <p>
                상주 서비스·캐시인지, 끝난 작업의 점유인지 확인하세요. 불필요한 점유로 확인된
                경우에만 정리를 검토합니다.
              </p>
            </details>
            <a href="#c2-hourly-overview">겹치는 시간대 확인 →</a>
          </article>
        )}
        {burst && (
          <article>
            <span className="c2-insight-kind">기간 평균과 시간대 평균 최고</span>
            <h3>{label(burst.row)}</h3>
            <p>
              기간 평균 <b>{Number(burst.row.activity_percent).toFixed(2)}%</b> · 시간대 평균 최고{' '}
              <b>{Number(burst.peak.activity_percent).toFixed(2)}%</b>
              <br />
              {time(burst.peak.start)}–{time(burst.peak.end).slice(-8)} KST
            </p>
            <details>
              <summary>조건에 따른 참고 안내 · AI 해석 아님</summary>
              <p>
                자원 축소나 작업 시간 변경을 검토하기 전에 이 구간의 작업 실행 기록·마감·메모리
                요구를 확인하세요.
              </p>
            </details>
            <a href="#c2-namespace-charts">시간대별 추이 확인 →</a>
          </article>
        )}
        {evidence.some((e) => !percentage(e.row.activity_percent)) && (
          <article>
            <span className="c2-insight-kind">관측 범위 확인</span>
            <h3>자료 부족은 사용률 0%가 아닙니다</h3>
            <p>
              현재 수치가 없는 대상은 사용 여부를 판단하지 않습니다. 실제 실행 대상이 없었는지,
              수집·Namespace 연결에 공백이 있었는지 확인하세요.
            </p>
            <a href="#c2-observation-coverage">대상별 관측 범위 →</a>
          </article>
        )}
        {!resident && !burst && evidence.every((e) => percentage(e.row.activity_percent)) && (
          <p>
            위 조건으로 강조할 관측은 없습니다. 아래 저장된 운영 해석과 대상별 근거를 확인하세요.
          </p>
        )}
      </div>
      <p className="c2-chart-note">
        연결 GPU의 관측이며 독점 사용량·회수 가능량이 아닙니다. 시간대 최고는 저장된 높은 활동률
        기준({burst ? String(burst.highActivity) + '%' : '보고서 선별 조건'})에 해당하는 관측이며
        위험도나 자원 부족 판정이 아닙니다.
      </p>
    </section>
  );
}

export function HourlyOverview({ value }: { value: Row }) {
  const evidence = operationalEvidence(value);
  const period = obj(value.time_range);
  const start = Date.parse(str(period.start)),
    end = Date.parse(str(period.end));
  const slots: string[] = [];
  // Longer stored reports remain available through the existing detailed charts.
  if (Number.isFinite(start) && end > start && end - start <= 31 * 86400000)
    for (let t = start; t + 3600000 <= end; t += 3600000) slots.push(new Date(t).toISOString());
  const days = [...new Set(slots.map((s) => time(s).slice(0, -9)))];
  const [picked, setPicked] = useState('');
  const day = days.includes(picked) ? picked : days[0];
  const shown = slots.filter((s) => time(s).slice(0, -9) === day);
  if (!evidence.length) return null;
  return (
    <section id="c2-hourly-overview" className="c2-hourly-overview">
      <header>
        <div>
          <h3>시간대별 활동과 메모리 점유</h3>
          <p>활동률 0–100% · 회색은 자료 없음 · 테두리는 같은 시간의 낮은 활동·높은 메모리</p>
        </div>
        {days.length > 1 && (
          <label>
            날짜{' '}
            <select value={day} onChange={(e) => setPicked(e.target.value)}>
              {days.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
        )}
      </header>
      {!!shown.length && (
        <div className="c2-heatmap-scroll">
          <table className="c2-heatmap">
            <caption>{day} KST · 각 칸은 1시간 · 포커스 또는 마우스로 수치 확인</caption>
            <thead>
              <tr>
                <th>Namespace / 모델</th>
                {shown.map((s) => (
                  <th key={s}>{time(s).slice(-8, -6)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {evidence.map((r) => (
                <tr key={r.key}>
                  <th scope="row">
                    {str(r.row.namespace)}
                    <small>
                      {str(r.row.cluster_id)} · {str(r.row.gpu_model)}
                    </small>
                  </th>
                  {shown.map((s) => {
                    const h = r.hours.find((h) => Date.parse(str(h.start)) === Date.parse(s));
                    const paired = h && r.paired.find((p) => p.hour === h);
                    const overlap = h && r.overlap.some((p) => p.hour === h);
                    const v = h ? Number(h.activity_percent) : null;
                    const text = `${label(r.row)} · ${time(s)} KST · 활동률 ${v === null ? '미확인' : v.toFixed(2) + '%'} · 메모리 ${paired ? paired.memory.toFixed(2) + '%' : '미확인'}${overlap ? ` · 활동률 ${r.low}% 미만·메모리 ${r.high}% 이상` : ''}`;
                    return (
                      <td key={s}>
                        <button
                          type="button"
                          className={`c2-heat-cell${overlap ? ' c2-heat-overlap' : ''}`}
                          aria-label={text}
                          style={{
                            background: v === null ? '#e5e8e6' : `hsl(87 57% ${96 - v * 0.65}%)`,
                          }}
                        >
                          <span className="c2-heat-tip">{text}</span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!shown.length && (
        <p>시간대 요약을 표시할 수 없는 기간입니다. 상세 그래프와 저장 근거를 확인하세요.</p>
      )}
      <details id="c2-observation-coverage" className="c2-coverage-details">
        <summary>대상별 유효 시간·기간 비교·동시 관측 범위</summary>
        <div className="aggregate-table-scroll">
          <table>
            <thead>
              <tr>
                <th>대상</th>
                <th>활동률 유효 시간</th>
                <th>이전 기간 비교</th>
                <th>낮은 활동·높은 메모리</th>
              </tr>
            </thead>
            <tbody>
              {evidence.map((r) => (
                <tr key={r.key}>
                  <th>{label(r.row)}</th>
                  <td>
                    {r.hours.length} /{' '}
                    {typeof r.row.expected_hours === 'number' ? r.row.expected_hours : '미확인'}시간
                  </td>
                  <td>{r.row.comparison_status === 'comparable' ? '비교 가능' : '비교 보류'}</td>
                  <td>
                    {percentage(r.low) && percentage(r.high) && r.paired.length
                      ? `${r.overlap.length}/${r.paired.length}개 동시 관측 시간대`
                      : '비교 자료 없음'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          동시 관측은 대상·모델·시작과 종료가 같은 시간대만 대조합니다. 기준은 보고서에 저장된 선별
          조건이며 할당 정책이 아닙니다. 누락 구간은 합산하거나 보간하지 않습니다.
        </p>
      </details>
    </section>
  );
}
