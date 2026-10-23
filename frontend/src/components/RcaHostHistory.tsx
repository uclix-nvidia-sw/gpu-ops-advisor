import { useState } from 'react';
import { obj, rows, str, strings, num, type Row } from '../lib/live';
import { formatRcaTime as formatDate } from '../lib/rcaTime';
import { intervalLabel } from '../lib/rcaOperatorView';
import { Ids, ToneBadge } from './RcaReportParts';

export function RcaHostHistory({ result, embedded = false }: { result: Row; embedded?: boolean }) {
  const history = obj(obj(result.quality).host_incident_history);
  const [days, setDays] = useState(14);
  const [code, setCode] = useState('');
  const [related, setRelated] = useState(embedded);
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
  const current = incidents.find((r) => r.current === true);
  const currentDevice = str(current?.device) || str(current?.gpu_uuid);
  const visible = incidents.filter(
    (r) =>
      (!code || strings(r.codes).includes(code)) &&
      (!related ||
        !currentDevice ||
        ((str(r.device) || str(r.gpu_uuid)) === currentDevice &&
          strings(r.codes).some((c) => strings(current?.codes).includes(c)))),
  );
  // Code → device → incidents. The current alert's code leads; each code's host-wide row
  // heads its own device rows, busiest device first.
  const byCode = new Map<string, Map<string, Row[]>>();
  visible.forEach((r) =>
    strings(r.codes)
      .filter((c) => !code || c === code)
      .forEach((c) => {
        const devices = byCode.get(c) || new Map<string, Row[]>();
        const d = str(r.device) || str(r.gpu_uuid);
        byCode.set(c, devices.set(d, [...(devices.get(d) || []), r]));
      }),
  );
  const hostRows = !related || !currentDevice;
  const curCodes = strings(current?.codes);
  const groups = [...byCode]
    .sort(
      ([a], [b]) =>
        Number(curCodes.includes(b)) - Number(curCodes.includes(a)) || a.localeCompare(b),
    )
    .flatMap(([c, devices]) => [
      ...(hostRows ? [{ c, device: '', host: true, items: [...devices.values()].flat() }] : []),
      ...[...devices]
        .sort((a, b) => b[1].length - a[1].length)
        .map(([device, items]) => ({ c, device, host: false, items })),
    ]);
  return (
    <section className="rca-host-history" aria-label="호스트 사건 이력">
      {embedded ? <h5>이전 사건과 RCA</h5> : <h4>4. 호스트 이력 · 반복된 사건</h4>}
      <p>
        {formatDate(new Date(cutoff).toISOString())} ~ {formatDate(str(period.end))} · 등록 사건{' '}
        {incidents.length}건{code && ` · 선택 코드 ${visible.length}건`}
        {related && currentDevice && ` · 동일 장치·오류 ${visible.length}건`}
      </p>
      <div className="rca-history-filters">
        {currentDevice && (
          <label>
            <input
              type="checkbox"
              checked={related}
              onChange={(e) => setRelated(e.target.checked)}
            />
            동일 장치·오류만 보기
          </label>
        )}
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
      {groups.length > 0 && (
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
              {groups.map(({ c, device, host, items }) => {
                const times = items
                  .map((r) => Date.parse(str(r.occurred_at)))
                  .sort((a, b) => a - b);
                const gaps = times.slice(1).map((t, i) => t - times[i]);
                return (
                  <tr key={`${c}|${host ? '*' : device}`}>
                    {host ? (
                      <td>
                        <strong>{c.toUpperCase()} · 호스트 전체</strong>
                      </td>
                    ) : (
                      <td style={hostRows ? { paddingLeft: '1.5em' } : undefined}>
                        {!hostRows && `${c.toUpperCase()} · `}
                        {device ? <Ids text={device} /> : '장치 정보 없음'}
                        {device === currentDevice && curCodes.includes(c) && (
                          <>
                            {' '}
                            <ToneBadge tone="warn" label="이번 장치" />
                          </>
                        )}
                      </td>
                    )}
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
              <th>알림 기준 시각</th>
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
                  {(str(r.device) || str(r.gpu_uuid)) && (
                    <span title={str(r.device) || str(r.gpu_uuid)}>
                      <Ids text={str(r.device) || str(r.gpu_uuid)} />
                    </span>
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
                  {str(obj(r.prior_rca).job_id) && (
                    <>
                      <br />
                      <a
                        href={`/analyses/${encodeURIComponent(str(obj(r.prior_rca).job_id))}#final-report`}
                      >
                        이전 RCA 열기
                      </a>
                      <br />
                      {str(obj(r.prior_rca).result_status) === 'partial' &&
                        '일부 자료로 작성된 보고서'}
                    </>
                  )}
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
