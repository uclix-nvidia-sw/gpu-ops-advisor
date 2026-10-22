import { obj, rows, str, num, strings, type Row } from '../lib/live';
import { formatRcaTime as formatDate } from '../lib/rcaTime';
import { intervalLabel, operatorView, shortGpu, type Window } from '../lib/rcaOperatorView';
import { ToneBadge } from './RcaReportParts';

const fmtNum = (v: number) => String(Math.round(v * 1000) / 1000);

export function RcaTriageObservations({
  result,
  onEvidence,
}: {
  result: Row;
  onEvidence?: (id: string) => void;
}) {
  const v = operatorView(result);
  if (!v) return null;
  const view = obj(obj(result.quality).triage_observations);
  const links = (value: unknown) =>
    onEvidence
      ? strings(value).map((id, i) => (
          <button className="text-link" key={id} onClick={() => onEvidence(id)}>
            원문 {i + 1}
          </button>
        ))
      : null;
  const windowText = (w: Window | null, unit: string) =>
    !w ? (
      <span className="rca-muted">표본 없음</span>
    ) : (
      <>
        {w.min === w.max
          ? `${fmtNum(w.min)} ${unit}`
          : `${fmtNum(w.min)} ~ ${fmtNum(w.max)} ${unit}`}
        <br />
        <small>
          {w.samples}개 · 마지막 {formatDate(w.end)}
        </small>
      </>
    );
  const start = Date.parse(v.timeline[0]?.at || '');
  const end = Date.parse(v.timeline[v.timeline.length - 1]?.at || '');
  const origin = Date.parse(v.eventTime || v.firstReport);
  return (
    <section className="rca-host-history" aria-label="사건 로그와 관련 지표">
      <h4>3. 관련 로그·메트릭 · {v.node}</h4>
      <p className="rca-muted">
        조회 구간 {formatDate(v.periodStart)} ~ {formatDate(v.periodEnd)}
      </p>
      <table className="rca-5w">
        <caption>육하원칙으로 본 이번 사건</caption>
        <tbody>
          <tr>
            <th>언제</th>
            <td>
              {v.eventTime ? (
                <>
                  <mark>오류 발생 {formatDate(v.eventTime)}</mark>
                  <br />
                </>
              ) : (
                <>
                  <mark>원본 이벤트 시각 미확인</mark> (조회 구간 이전 발생 가능)
                  <br />
                </>
              )}
              보고 {formatDate(v.firstReport)} ~ {formatDate(v.lastReport)}
            </td>
          </tr>
          <tr>
            <th>어디서</th>
            <td>
              CPC <strong>{v.cluster || '—'}</strong> · 노드 <strong>{v.node}</strong>
            </td>
          </tr>
          <tr>
            <th>무엇이</th>
            <td>
              <strong>
                {v.family === 'nvswitch' ? 'NVSwitch ' : 'GPU '}PCI {v.alertPci || '—'}
              </strong>
              {v.alertGpu && <span title={v.alertUuid}> · {v.alertGpu}</span>}
            </td>
          </tr>
          <tr>
            <th>무엇을</th>
            <td>
              <mark>{v.codes.join(', ')}</mark> {shortGpu(v.message)}
            </td>
          </tr>
          <tr>
            <th>어떻게</th>
            <td>
              보고 {v.reports}건 ·{' '}
              {v.ongoing ? <mark>조회 종료까지 계속 보고됨</mark> : '마지막 보고 뒤 추가 보고 없음'}{' '}
              · {v.findings[2].verdict}
            </td>
          </tr>
          <tr>
            <th>왜</th>
            <td>
              {v.causeNote || '원인 후보 정보 없음'}{' '}
              <ToneBadge tone="unknown" label="원인 미확정" />
            </td>
          </tr>
        </tbody>
      </table>

      {v.timeline.length > 1 && end > start && (
        <figure className="rca-timeline" aria-label="사건 타임라인">
          <figcaption>사건 타임라인 · 기록 순서는 원인 순서가 아닙니다</figcaption>
          <div className="rca-track" aria-hidden="true">
            {v.timeline.map((item, i) => (
              <span
                key={i}
                className={`rca-dot tone-${item.tone}`}
                style={{ left: `${((Date.parse(item.at) - start) / (end - start)) * 100}%` }}
                title={`${formatDate(item.at)} ${item.label}`}
              />
            ))}
          </div>
          <ol>
            {v.timeline.map((item, i) => (
              <li key={i}>
                <span className={`rca-dot tone-${item.tone}`} aria-hidden="true" />
                <time>{formatDate(item.at)}</time>
                {Number.isFinite(origin) && (
                  <small>
                    {' '}
                    ({Date.parse(item.at) >= origin ? '+' : '−'}
                    {intervalLabel(Math.abs(Date.parse(item.at) - origin))})
                  </small>
                )}{' '}
                {item.label}
              </li>
            ))}
          </ol>
        </figure>
      )}

      {rows(view.switch_pci).map((r, i) => (
        <p key={i}>
          NVSwitch PCI 대조 · 로그/알림: {strings(r.reported_pci).join(', ')} · Grafana PCI 라벨
          조회:{' '}
          {strings(r.observed_pci).length
            ? strings(r.observed_pci).join(', ')
            : r.status === 'empty'
              ? '해당 구간에 일치하는 시계열 없음'
              : '조회 상세 참조'}{' '}
          {links(r.evidence_refs)}
        </p>
      ))}
      <div className="rca-history-table">
        <table>
          <caption>오류 로그 · 같은 내용은 묶고 처음·마지막 보고 시각을 표시합니다.</caption>
          <thead>
            <tr>
              <th>오류·장치</th>
              <th>발생 시각 · 보고 구간</th>
              <th>보고</th>
              <th>로그</th>
            </tr>
          </thead>
          <tbody>
            {rows(view.logs).map((r, i) => (
              <tr key={i}>
                <td>
                  <mark>{str(r.code).toUpperCase()}</mark>
                  <br />
                  {str(r.device)}
                </td>
                <td>
                  {strings(r.event_times).map((at) => (
                    <div key={at}>
                      <strong>발생: {formatDate(at)}</strong>
                    </div>
                  ))}
                  보고: {formatDate(str(r.first))}
                  <br />~ {formatDate(str(r.last))}
                </td>
                <td>{num(r.reports)}건</td>
                <td>
                  <details>
                    <summary>{shortGpu(str(r.message)).slice(0, 160)}</summary>
                    <pre>{str(r.message)}</pre>
                  </details>
                  {links(r.evidence_refs)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {v.metrics.length > 0 && (
        <div className="rca-history-table">
          <table>
            <caption>
              관련 메트릭 ·{' '}
              {view.metric_scope === 'node_gpu_context'
                ? '같은 노드 GPU별 관측'
                : '보고된 GPU와 대응한 관측'}{' '}
              · 사건 기준 {v.boundary ? formatDate(v.boundary) : '시각 없음'}
            </caption>
            <thead>
              <tr>
                <th>지표·단위</th>
                <th>GPU</th>
                <th>사건 전</th>
                <th>사건 이후</th>
                <th>판독</th>
              </tr>
            </thead>
            <tbody>
              {v.metrics.map((m, i) => (
                <tr key={i}>
                  <td>
                    {m.name}
                    <br />
                    <small>{m.unit}</small>
                  </td>
                  <td>
                    {m.gpus.length === 1 ? (
                      m.gpus[0]
                    ) : (
                      <details>
                        <summary>GPU {m.gpus.length}개 · 동일 관측값</summary>
                        {m.gpus.map((g) => (
                          <p key={g}>{g}</p>
                        ))}
                      </details>
                    )}
                  </td>
                  {m.whole ? (
                    <td colSpan={2}>조회 구간 전체: {windowText(m.whole, m.unit)}</td>
                  ) : (
                    <>
                      <td>{windowText(m.before, m.unit)}</td>
                      <td>{windowText(m.after, m.unit)}</td>
                    </>
                  )}
                  <td>
                    <ToneBadge tone={m.tone} />
                    <p>{m.reading}</p>
                    {links(m.refs)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
