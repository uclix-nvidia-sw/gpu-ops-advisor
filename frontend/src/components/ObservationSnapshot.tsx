import type { ReactNode } from 'react';
import { obj, rows, str } from '../lib/live';

export function RawJson({ value }: { value: unknown }) {
  return (
    <details className="raw-json">
      <summary>원본 JSON</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function Chips({ value }: { value: unknown }) {
  return (
    <div className="snapshot-chips">
      {Object.entries(obj(value))
        .filter(([key]) => !['__tenant_id__', 'checksum', 'request_id'].includes(key))
        .map(([key, v]) => (
          <span key={key}>
            {key}={String(v)}
          </span>
        ))}
    </div>
  );
}
function time(value: unknown) {
  const text = String(value ?? '');
  const date = /^\d{16,20}$/.test(text)
    ? new Date(Number(BigInt(text) / 1000000n))
    : new Date(typeof value === 'number' ? value * 1000 : text);
  return Number.isFinite(date.getTime())
    ? date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST'
    : '시각 미확인';
}
export function ObservationSnapshot({ value, fallback }: { value: unknown; fallback: ReactNode }) {
  const source = obj(value);
  const data = Array.isArray(value)
    ? rows(value)
    : Array.isArray(source.data)
      ? rows(source.data)
      : rows(obj(source.data).result ?? source.result);
  if (data.length && data.every((row) => typeof row.line === 'string'))
    return (
      <>
        <div className="table-wrap">
          <table className="snapshot-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>health</th>
                <th>reason</th>
                <th>node</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, index) => {
                let parsed = {};
                try {
                  parsed = JSON.parse(str(row.line));
                } catch {
                  /* Plain logs remain available in raw view. */
                }
                const attributes = obj(obj(parsed).attributes),
                  resources = obj(obj(parsed).resources);
                return (
                  <tr key={index}>
                    <td>
                      {time(row.timestamp)}
                      {!!obj(row.labels).test_id && <span>테스트 알람</span>}
                    </td>
                    <td>{str(attributes.health, '미확인')}</td>
                    <td>
                      <p>{str(attributes.reason, '사유 미확인')}</p>
                      <Chips value={row.labels} />
                      <RawJson value={Object.keys(obj(parsed)).length ? parsed : row.line} />
                    </td>
                    <td>{str(resources['k8s.node.name'], str(obj(row.labels).node, '미확인'))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <RawJson value={value} />
      </>
    );
  if (
    data.length &&
    data.every((row) => row.metric && (Array.isArray(row.values) || Array.isArray(row.value)))
  )
    return (
      <>
        <div className="table-wrap">
          <table className="snapshot-table">
            <thead>
              <tr>
                <th>시계열 라벨</th>
                <th>원본 표본</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, index) => (
                <tr key={index}>
                  <td>
                    <Chips value={row.metric} />
                  </td>
                  <td>
                    <RawJson value={row.values ?? row.value} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <RawJson value={value} />
      </>
    );
  return (
    <>
      {fallback}
      <RawJson value={value} />
    </>
  );
}
