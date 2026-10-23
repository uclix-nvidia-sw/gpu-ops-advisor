import { Fragment } from 'react';
import { obj, rows, str, num, strings, type Row } from '../lib/live';
import { formatRcaTime as formatDate } from '../lib/rcaTime';
import {
  intervalLabel,
  operatorView,
  valueText,
  type MetricRow,
  type Window,
} from '../lib/rcaOperatorView';
import { Ids, ToneBadge } from './RcaReportParts';

// Raw rows shown before the rest fold; eight covers one metric per GPU on 8-GPU nodes.
const RAW_ROWS = 8;

const rangeText = (w: Window, unit: string) =>
  w.min === w.max
    ? valueText(w.min, unit)
    : `${valueText(w.min, unit)} ~ ${valueText(w.max, unit)}`;

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
        {rangeText(w, unit)}
        <br />
        <small>
          {w.samples}개 · 마지막 {formatDate(w.end)}
        </small>
      </>
    );
  const rawRow = (m: MetricRow, i: number) => {
    const set = v.gpuSet(m.uuids);
    return (
      <tr key={i}>
        <td>{m.name}</td>
        <td>
          {set}
          {/* GPUs without an index stay identifiable by UUID. */}
          {!/모두|번$/.test(set) &&
            m.gpus.map((g) => (
              <small key={g}>
                <br />
                <Ids text={g} />
              </small>
            ))}
        </td>
        {m.whole ? (
          <td colSpan={2}>조회 구간 전체 {m.wholeText}</td>
        ) : (
          <>
            <td>{m.beforeText || <span className="rca-muted">표본 없음</span>}</td>
            <td>{m.afterText || <span className="rca-muted">표본 없음</span>}</td>
          </>
        )}
        <td>
          <ToneBadge tone={m.tone} label={m.tag} /> {links(m.refs)}
        </td>
      </tr>
    );
  };
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
                <mark>오류 발생 {formatDate(v.eventTime)}</mark>
              ) : v.onsetText ? (
                <mark>{v.onsetText}</mark>
              ) : (
                <>
                  <mark>시작 시각 미확인</mark> (조회 구간보다 먼저 시작됐을 수 있음)
                </>
              )}
              <br />
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
                {v.family === 'nvswitch'
                  ? 'NVSwitch '
                  : `GPU ${v.gpuIndex ? `${v.gpuIndex} ` : ''}`}
                PCI <code className="rca-id">{v.alertPci || '—'}</code>
              </strong>
              {v.alertUuid && (
                <>
                  {' '}
                  · <code className="rca-id">{v.alertUuid}</code>
                </>
              )}
              {(v.gpuModel || v.driver) && (
                <>
                  <br />
                  <small>
                    {[v.gpuModel, v.driver && `드라이버 ${v.driver}`].filter(Boolean).join(' · ')}
                  </small>
                </>
              )}
            </td>
          </tr>
          <tr>
            <th>무엇을</th>
            <td>
              <mark>{v.codes.join(', ')}</mark> <Ids text={v.message} />
            </td>
          </tr>
          {(v.workloads.length > 0 || v.metrics.length > 0) && (
            <tr>
              <th>누구에게</th>
              <td>
                {!v.workloads.some((w) => w.atIncident) && (
                  <div>
                    {v.podsKnown
                      ? `사건 시각에 ${v.family === 'nvswitch' ? '노드 GPU' : '이 GPU'}를 쓰던 파드가 없습니다 (작업 영향 미관측)`
                      : '수집한 지표에 파드 정보가 없어 확인하지 못했습니다 — kubectl get pods -A -o wide로 확인'}
                  </div>
                )}
                {v.workloads
                  .filter((w) => w.atIncident)
                  .map((w) => (
                    <div key={w.name}>
                      <strong>{w.name}</strong> 작업이 이{' '}
                      {v.family === 'nvswitch' ? '노드 GPU' : 'GPU'}를 사용 중 · {w.gpus}
                      {w.gpuCount > 1 && ` (${w.gpuCount}개 함께 사용 — 파드 단위로 영향 확인)`}
                    </div>
                  ))}
                {v.neighbours.length > 0 && (
                  <div>
                    같은 노드 다른 GPU 작업:{' '}
                    {v.neighbours.map((w) => `${w.name} (${w.gpus})`).join(', ')}
                  </div>
                )}
                <small>DCGM 지표에 기록된 파드 라벨 기준(관측) · 할당 정보가 아닙니다</small>
              </td>
            </tr>
          )}
          <tr>
            <th>어떻게</th>
            <td>
              보고 {v.reports}건 ·{' '}
              {v.ongoing ? <mark>조회 종료까지 계속 보고됨</mark> : '마지막 보고 뒤 추가 보고 없음'}
              {v.telemetryHeadline &&
                ` · ${v.telemetryHeadline}${v.multiGpu ? ' (아래 GPU별 표)' : ''}`}
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
            {[...v.logs, ...v.otherLogs].map((r, i) => (
              <Fragment key={i}>
                {i === v.logs.length && (
                  <tr>
                    <th colSpan={4}>같은 노드의 다른 오류 (참고 · 이 보고서 대상 아님)</th>
                  </tr>
                )}
                <tr className={i >= v.logs.length ? 'rca-muted' : undefined}>
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
                      <summary>
                        <Ids text={str(r.message)} />
                      </summary>
                      <pre>{str(r.message)}</pre>
                    </details>
                    {links(r.evidence_refs)}
                  </td>
                </tr>
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {v.metrics.length > 0 && v.multiGpu && (
        <div className="rca-history-table">
          <table>
            <caption>
              GPU별 지표 · 사건 직전 → 사건 후 · 사건 기준{' '}
              {v.boundary ? formatDate(v.boundary) : '시각 없음'} · 판정이 같은 GPU는 한 줄로 묶음
            </caption>
            <thead>
              <tr>
                <th style={{ width: '22%' }}>GPU</th>
                <th>지표 변화 (직전 → 사건 후)</th>
                <th style={{ width: '24%' }}>판정</th>
              </tr>
            </thead>
            <tbody>
              {v.gpuRows.map((r) => (
                <tr key={r.gpus}>
                  <td>
                    <strong>{r.gpus}</strong>
                    {r.pci && (
                      <>
                        <br />
                        <small>
                          <code className="rca-id">{r.pci}</code>
                        </small>
                      </>
                    )}
                  </td>
                  <td>
                    {r.lines.map((line) => (
                      <div key={line}>{line}</div>
                    ))}
                  </td>
                  <td>
                    <ToneBadge tone={r.tone} label={r.tag} />
                    {r.once && <small> 사건 뒤 표본 1회</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {v.gpuCommon.length > 0 && (
            <p className="rca-muted">모든 GPU 공통: {v.gpuCommon.join(' · ')}</p>
          )}
        </div>
      )}
      {v.metrics.length > 0 && !v.multiGpu && (
        <div className="rca-history-table">
          <table>
            <caption>
              관련 메트릭 · 사건 기준 {v.boundary ? formatDate(v.boundary) : '시각 없음'}
            </caption>
            <thead>
              <tr>
                <th style={{ width: '20%' }}>지표</th>
                <th style={{ width: '24%' }}>사건 전</th>
                <th style={{ width: '18%' }}>사건 후</th>
                <th>한 줄 해석</th>
              </tr>
            </thead>
            <tbody>
              {v.metrics.map((m, i) => (
                <tr key={i}>
                  <td>{m.name}</td>
                  {m.whole ? (
                    <td colSpan={2}>조회 구간 전체: {windowText(m.whole, m.unit)}</td>
                  ) : (
                    <>
                      <td>
                        {m.before ? (
                          <>
                            {rangeText(m.before, m.unit)}
                            <br />
                            <small>직전 {valueText(m.before.last, m.unit)}</small>
                          </>
                        ) : (
                          <span className="rca-muted">표본 없음</span>
                        )}
                      </td>
                      <td>
                        <ToneBadge
                          tone={m.tone}
                          label={m.after ? rangeText(m.after, m.unit) : '표본 없음'}
                        />
                      </td>
                    </>
                  )}
                  <td>
                    <strong>{m.tag}</strong> {m.short}
                    <div>{links(m.refs)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {v.metrics.length > 0 && v.multiGpu && (
        <div className="rca-history-table">
          <table>
            <caption>GPU별 원자료 · 한 줄에 한 지표 · 값이 같은 GPU는 묶음</caption>
            <thead>
              <tr>
                <th style={{ width: '28%' }}>지표</th>
                <th style={{ width: '16%' }}>GPU</th>
                <th>사건 전</th>
                <th>사건 후</th>
                <th style={{ width: '18%' }}>판정</th>
              </tr>
            </thead>
            <tbody>{v.metrics.slice(0, RAW_ROWS).map(rawRow)}</tbody>
          </table>
          {v.metrics.length > RAW_ROWS && (
            <details>
              <summary>나머지 {v.metrics.length - RAW_ROWS}행</summary>
              <table>
                <tbody>{v.metrics.slice(RAW_ROWS).map(rawRow)}</tbody>
              </table>
            </details>
          )}
        </div>
      )}
      {v.workloads.length > 0 && (
        <p className="rca-muted">
          이 {v.family === 'nvswitch' ? '노드의 GPU' : 'GPU'}를 쓴 작업(DCGM 지표 라벨 기준):{' '}
          {v.workloads.map((w, i) => (
            <span key={w.name + w.first}>
              {i > 0 && ' → '}
              {formatDate(w.first).slice(-12)} <strong>{w.name}</strong>
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
