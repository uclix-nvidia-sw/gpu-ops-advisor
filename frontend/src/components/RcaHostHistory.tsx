import { useState } from 'react';
import { obj, rows, str, strings, num, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';

function intervalLabel(ms: number) {
  if (ms < 60000) return `${Math.round(ms / 1000)}초`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}분`;
  if (ms < 86400000) return `${(ms / 3600000).toFixed(1)}시간`;
  return `${(ms / 86400000).toFixed(1)}일`;
}

export function RcaHostHistory({ result }: { result: Row }) {
  const history = obj(obj(result.quality).host_incident_history);
  const [days, setDays] = useState(14);
  const [code, setCode] = useState('');
  if (history.schema !== 'rca-host-history/1') return null;
  const period = obj(history.period);
  const end = Date.parse(str(period.end));
  const cutoff = Math.max(Date.parse(str(period.start)), end - days * 86400000);
  if (!Number.isFinite(cutoff) || !Number.isFinite(end)) return null;
  const incidents = rows(history.rows).filter((r) => Date.parse(str(r.occurred_at)) >= cutoff);
  const counts = new Map<string, number>();
  incidents.forEach((r) =>
    strings(r.codes).forEach((c) => counts.set(c, (counts.get(c) || 0) + 1)),
  );
  const visible = incidents.filter((r) => !code || strings(r.codes).includes(code));
  const groups = new Map<string, Row[]>();
  visible.forEach((r) =>
    strings(r.codes)
      .filter((c) => !code || c === code)
      .forEach((c) => {
        const hostKey = `${c.toUpperCase()} · 호스트 전체`;
        groups.set(hostKey, [...(groups.get(hostKey) || []), r]);
        if (str(r.gpu_uuid)) {
          const key = `${c.toUpperCase()} · ${str(r.gpu_uuid)}`;
          groups.set(key, [...(groups.get(key) || []), r]);
        }
      }),
  );
  return (
    <section className="rca-host-history" aria-label="호스트 사건 이력">
      <h4>4. 호스트 이력 · 반복된 사건</h4>
      <p>
        {formatDate(new Date(cutoff).toISOString())} ~ {formatDate(str(period.end))} · 등록 사건{' '}
        {incidents.length}건{code && ` · 선택 코드 ${visible.length}건`}
      </p>
      <div className="rca-history-filters">
        <label>
          조회 기간{' '}
          <select
            value={days}
            onChange={(e) => {
              setDays(Number(e.target.value));
              setCode('');
            }}
          >
            <option value={7}>최근 7일</option>
            <option value={14}>최근 14일</option>
          </select>
        </label>
        <label>
          오류 코드{' '}
          <select value={code} onChange={(e) => setCode(e.target.value)}>
            <option value="">전체</option>
            {[...counts].sort().map(([c, n]) => (
              <option key={c} value={c}>
                {c.toUpperCase()} · {n}건
              </option>
            ))}
          </select>
        </label>
      </div>
      {groups.size > 0 && (
        <div className="rca-history-table">
          <table>
            <caption>코드·대상별 등록 건수와 최근 간격</caption>
            <thead>
              <tr>
                <th>코드·대상</th>
                <th>등록 사건</th>
                <th>최근 등록 간격</th>
                <th>간격 범위</th>
              </tr>
            </thead>
            <tbody>
              {[...groups].map(([key, items]) => {
                const times = items
                  .map((r) => Date.parse(str(r.occurred_at)))
                  .sort((a, b) => a - b);
                const gaps = times.slice(1).map((t, i) => t - times[i]);
                return (
                  <tr key={key}>
                    <td>
                      {key.endsWith('호스트 전체') ? (
                        key
                      ) : (
                        <details>
                          <summary>{key.split(' · ')[0]} · 같은 GPU</summary>
                          {key}
                        </details>
                      )}
                    </td>
                    <td>{items.length}건</td>
                    <td>{gaps.length ? intervalLabel(gaps[gaps.length - 1]) : '—'}</td>
                    <td>
                      {gaps.length
                        ? `${intervalLabel(Math.min(...gaps))} ~ ${intervalLabel(Math.max(...gaps))}`
                        : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="rca-history-table">
        <table className="rca-incident-table">
          <caption>
            로그 줄 수가 아닌 Incident ID별 사건입니다. 보고 구간은 알림 관측의 처음~마지막
            시각입니다.
          </caption>
          <thead>
            <tr>
              <th>사건 시각</th>
              <th>코드·대상</th>
              <th>보고 구간</th>
              <th>핵심 메시지</th>
              <th>원문</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={str(r.incident_id)}>
                <td>
                  {r.current === true && <strong>이번 사건 · </strong>}
                  {formatDate(str(r.occurred_at))}
                </td>
                <td>
                  {strings(r.codes).join(', ').toUpperCase() || '기타 오류'}
                  <br />
                  {str(r.gpu_uuid) && (
                    <details>
                      <summary>GPU 식별자</summary>
                      {str(r.gpu_uuid)}
                    </details>
                  )}
                </td>
                <td>
                  {formatDate(str(r.first_report))}
                  <br />~ {formatDate(str(r.last_report))}
                  {r.last_report_capped === true && ' (조회 종료)'}
                  <br />
                  {typeof r.reported_span_seconds === 'number'
                    ? `${Math.round(num(r.reported_span_seconds) / 60)}분 관측`
                    : ''}
                </td>
                <td>
                  <details>
                    <summary>
                      {str(r.reason)
                        .replace(/GPU-[a-f\d-]{36}/gi, '')
                        .slice(0, 110)}
                    </summary>
                    {str(r.reason)}
                  </details>
                </td>
                <td>
                  <a href={`/incidents/${encodeURIComponent(str(r.incident_id))}`}>사건 열기</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!visible.length && <p>표시할 사건이 없습니다. 기간과 오류 코드 선택을 확인하세요.</p>}
      {history.complete !== true && (
        <p>수집된 최근 사건을 표시합니다. 조회 범위·상한은 수집 상세에서 확인할 수 있습니다.</p>
      )}
    </section>
  );
}
