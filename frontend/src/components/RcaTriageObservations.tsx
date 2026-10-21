import { obj, rows, str, num, strings, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';

export function RcaTriageObservations({
  result,
  onEvidence,
}: {
  result: Row;
  onEvidence?: (id: string) => void;
}) {
  const view = obj(obj(result.quality).triage_observations);
  if (view.schema !== 'rca-triage-observations/1') return null;
  // Collapse only identical summaries; retain each GPU and its original evidence.
  const groups = new Map<string, Row[]>();
  for (const metric of rows(view.metrics)) {
    const key = JSON.stringify(
      ['name', 'unit', 'min', 'max', 'last_value', 'first', 'last', 'samples'].map(
        (field) => metric[field],
      ),
    );
    groups.set(key, [...(groups.get(key) || []), metric]);
  }
  const period = obj(view.period);
  const target = obj(view.target);
  const links = (value: unknown) =>
    onEvidence
      ? strings(value).map((id, i) => (
          <button className="text-link" key={id} onClick={() => onEvidence(id)}>
            원문 {i + 1}
          </button>
        ))
      : null;
  return (
    <section className="rca-host-history" aria-label="사건 로그와 관련 지표">
      <h4>3. 관련 로그·메트릭 · {str(target.node) || str(target.machine_id)}</h4>
      <p>
        {formatDate(str(period.start))} ~ {formatDate(str(period.end))}
      </p>
      <div className="rca-history-table">
        <table>
          <caption>동일 내용은 묶고, 처음·마지막 보고 시각과 원문을 함께 표시합니다.</caption>
          <thead>
            <tr>
              <th>오류·장치</th>
              <th>보고 구간</th>
              <th>수신</th>
              <th>로그</th>
            </tr>
          </thead>
          <tbody>
            {rows(view.logs).map((r, i) => (
              <tr key={i}>
                <td>
                  {str(r.code).toUpperCase()}
                  <br />
                  {str(r.device)}
                </td>
                <td>
                  {formatDate(str(r.first))}
                  <br />~ {formatDate(str(r.last))}
                </td>
                <td>{num(r.reports)}건</td>
                <td>
                  <details>
                    <summary>{str(r.message).slice(0, 160)}</summary>
                    <pre>{str(r.message)}</pre>
                  </details>
                  {links(r.evidence_refs)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows(view.metrics).length > 0 && (
        <div className="rca-history-table">
          <table>
            <caption>
              관련 메트릭 ·{' '}
              {view.metric_scope === 'node_gpu_context'
                ? '같은 노드 GPU별 관측'
                : '보고된 GPU와 대응한 관측'}
            </caption>
            <thead>
              <tr>
                <th>지표·단위</th>
                <th>GPU</th>
                <th>조회 구간의 관측 결과</th>
                <th>관측 시각·표본</th>
              </tr>
            </thead>
            <tbody>
              {[...groups.values()].map((group, i) => {
                const m = group[0];
                return (
                  <tr key={i}>
                    <td>
                      {str(m.name)}
                      <br />
                      {m.unit === 'bytes_per_second'
                        ? 'B/s'
                        : m.unit === 'enum'
                          ? '상태 코드'
                          : str(m.unit)}
                    </td>
                    <td>
                      {group.length === 1 ? (
                        <details>
                          <summary>대상 GPU</summary>
                          {str(m.gpu_uuid)}
                        </details>
                      ) : (
                        <details>
                          <summary>GPU {group.length}개 · 동일 관측값</summary>
                          {group.map((item, index) => (
                            <p key={index}>
                              {str(item.gpu_uuid)} {links(item.evidence_refs)}
                            </p>
                          ))}
                        </details>
                      )}
                    </td>
                    <td>
                      {typeof m.min !== 'number' || typeof m.max !== 'number' ? (
                        '수치 표본 없음'
                      ) : m.unit === 'enum' || m.unit === 'state' ? (
                        m.min === m.max ? (
                          `상태 코드 ${m.min} · 관측 내 변화 없음`
                        ) : (
                          '여러 상태 코드 관측 · 원문에서 전환 확인'
                        )
                      ) : typeof m.min !== 'number' || typeof m.max !== 'number' ? (
                        '수치 표본 없음'
                      ) : m.min === m.max ? (
                        `수집된 표본 모두 ${m.min} ${str(m.unit) === 'bytes_per_second' ? 'B/s' : str(m.unit)}`
                      ) : (
                        <>
                          관측 범위 {m.min} ~ {m.max}{' '}
                          {str(m.unit) === 'bytes_per_second' ? 'B/s' : str(m.unit)}
                          <br />
                          마지막 표본 {String(m.last_value ?? '—')}
                        </>
                      )}
                    </td>
                    <td>
                      {formatDate(str(m.first))} ~ {formatDate(str(m.last))}
                      <br />
                      {num(m.samples)}개 {links(m.evidence_refs)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
