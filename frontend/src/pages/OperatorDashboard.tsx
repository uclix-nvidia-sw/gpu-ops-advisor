import { Link } from 'react-router-dom';
import { QueryState } from '../components/live';
import {
  DeviceText,
  ErrorTitle,
  RcaLink,
  RepeatBadge,
  WINDOW_DAYS,
  dateTime,
  useRecentIncidents,
} from '../components/IncidentOverview';
import { rows, str, useResource } from '../lib/live';
import {
  CATEGORIES,
  ago,
  categorySummary,
  dailyCounts,
  dayKey,
  deviceRepeats,
  kindText,
  nodeStats,
  titleText,
  windowDays,
} from '../lib/incidentOverview';

/** Classic-mode dashboard: what is firing now, where faults repeat, and the trend. */
export function OperatorDashboard() {
  const { query, views, now, truncated } = useRecentIncidents();
  const modules = useResource('/service-status');
  const days = windowDays(now, WINDOW_DAYS);
  const today = dayKey(now);
  const firing = views.filter((v) => v.firing && !v.stale);
  const stale = views.filter((v) => v.stale);
  const todays = views.filter((v) => dayKey(v.at) === today);
  const repeats = deviceRepeats(views, days);
  const hot = repeats.filter((d) => d.count >= 3);
  const daily = dailyCounts(views, days);
  const total = (counts: Record<string, number>) =>
    Object.values(counts).reduce((a, b) => a + b, 0);
  const maxDay = Math.max(...daily.map((d) => total(d.counts)), 1);
  const maxDevice = Math.max(...repeats.map((d) => d.count), 1);
  const status = (module: string) =>
    str(rows(modules.data?.items).find((m) => m.module === module)?.status);
  return (
    <div className="page oh-page">
      <div className="oh-head-row">
        <div>
          <div className="oh-eyebrow">GPU OPERATIONS</div>
          <h1 tabIndex={-1}>운영 대시보드</h1>
          <p className="oh-sub">
            GPU 서버 장애 현황 · 최근 {WINDOW_DAYS}일 · 기준 {dateTime(now)} KST
          </p>
        </div>
        <Link className="button primary" to="/cases">
          사건 · RCA 보기 →
        </Link>
      </div>
      <QueryState query={query}>
        {truncated && (
          <p className="muted">
            사건이 많아 최근 일부만 집계했습니다. 사건 화면에서 범위를 좁혀 확인하세요.
          </p>
        )}
        <section className="oh-today" aria-label="오늘 한눈에">
          <span className="k">오늘 한눈에</span>
          {firing.length ? (
            <p className="alert">
              지금 장애 발생 중 {firing.length}건:{' '}
              {firing
                .map((v) => `${v.node} ${kindText(v.kind)} (${titleText({ ...v, codeText: '' })})`)
                .join(', ')}{' '}
              — 해당 장치를 쓰는 작업은 영향을 받았을 수 있습니다.
            </p>
          ) : (
            <p>지금 발생 중인 장애는 없습니다.</p>
          )}
          <p>
            오늘 장애 {todays.length}건{todays.length ? `: ${categorySummary(todays)}` : ''}.
            {stale.length > 0 && ` 해제 신호 없이 남은 '확인 필요' ${stale.length}건.`}
          </p>
          {repeats[0] && (
            <p>
              최근 {WINDOW_DAYS}일 가장 잦은 곳: {repeats[0].node} {kindText(repeats[0].kind)}{' '}
              {repeats[0].device} ({repeats[0].name}, {repeats[0].count}회).
            </p>
          )}
        </section>
        <div className="oh-kpis">
          <Link className="oh-kpi red" to="/cases?focus=firing">
            <span>지금 발생 중</span>
            <strong>{firing.length}</strong>
            <small>알림이 아직 해제되지 않은 사건</small>
          </Link>
          <Link className="oh-kpi amber" to="/cases?focus=stale">
            <span>확인 필요</span>
            <strong>{stale.length}</strong>
            <small>하루 넘게 '발생 중' · 해제 신호 없음</small>
          </Link>
          <Link className="oh-kpi" to="/cases?focus=today">
            <span>오늘 사건</span>
            <strong>{todays.length}</strong>
            <small>{categorySummary(todays) || '오늘 사건 없음'}</small>
          </Link>
          <Link className="oh-kpi" to="/cases?view=device">
            <span>반복 장치 ({WINDOW_DAYS}일 3회 이상)</span>
            <strong>{hot.length}</strong>
            <small>공급사 전달 검토 대상</small>
          </Link>
        </div>
        <section className="panel oh-dark">
          <div className="oh-ph">
            <h2>지금 대응할 사건</h2>
            <p>
              알림이 발생 중인 사건입니다. 런북 순서의 첫 단계부터 진행하고, 근거는 RCA 보고서에서
              확인합니다.
            </p>
          </div>
          <div className="oh-pad">
            {firing.length ? (
              firing.map((v) => (
                <article className="oh-now" key={v.id}>
                  <h3>
                    <ErrorTitle v={v} />
                  </h3>
                  <div className="meta">
                    <DeviceText v={v} /> · {ago(v.at, now)} 전 시작 <RepeatBadge v={v} />
                  </div>
                  <div className="act">
                    NVIDIA 즉시 조치 분류: <b>{v.label?.action || '런북 순서대로 확인'}</b>
                  </div>
                  {!!v.label?.steps.length && (
                    <ol className="oh-steps" aria-label="런북 대응 순서">
                      {v.label.steps.map((s, i) => (
                        <li key={s}>
                          {i + 1}. {s}
                        </li>
                      ))}
                    </ol>
                  )}
                  <div className="oh-actions">
                    <RcaLink v={v} button />
                    {v.kind !== 'host' && (
                      <Link
                        className="button"
                        to={`/cases?device=${encodeURIComponent(v.deviceKey)}`}
                      >
                        이 {kindText(v.kind)} 사건 이력
                      </Link>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <p className="muted">지금 발생 중인 알림이 없습니다.</p>
            )}
          </div>
        </section>
        <div className="oh-grid">
          <section className="panel">
            <div className="oh-ph">
              <h2>반복 장치 상위</h2>
              <p>최근 {WINDOW_DAYS}일 같은 장치·같은 오류. 3회 이상은 공급사 전달 검토</p>
            </div>
            <div className="oh-pad oh-bars">
              {repeats.length ? (
                repeats.slice(0, 8).map((d) => (
                  <Link className="b" key={d.key} to={`/cases?device=${encodeURIComponent(d.key)}`}>
                    <span>
                      <b>{d.node}</b> {kindText(d.kind)} <code className="oh-code">{d.device}</code>{' '}
                      · {d.codeText}
                    </span>
                    <span
                      className={`bar ${d.kind}`}
                      style={{ width: `${(d.count / maxDevice) * 100}%` }}
                    />
                    <b className="n">{d.count}</b>
                  </Link>
                ))
              ) : (
                <p className="muted">반복된 장치가 없습니다.</p>
              )}
            </div>
          </section>
          <section className="panel">
            <div className="oh-ph">
              <h2>최근 {WINDOW_DAYS}일 사건 추이</h2>
              <p>하루 단위 사건 수 (알림 기준, KST) · 막대에 올리면 분류별 수</p>
            </div>
            <div className="oh-pad">
              <div className="oh-chart" role="img" aria-label="날짜별 사건 수">
                {daily.map((d) => (
                  <div
                    className="c"
                    key={d.day}
                    title={`${d.day} · ${CATEGORIES.map((c) => `${c.name} ${d.counts[c.key]}`).join(' · ')}`}
                  >
                    {CATEGORIES.map((c) =>
                      d.counts[c.key] ? (
                        <i
                          key={c.key}
                          className={`cat-${c.key}`}
                          style={{ height: `${(d.counts[c.key] / maxDay) * 120}px` }}
                        />
                      ) : null,
                    )}
                  </div>
                ))}
              </div>
              <div className="oh-xl">
                {daily.map((d) => (
                  <span key={d.day}>{d.day.slice(8)}</span>
                ))}
              </div>
              <ul className="oh-legend">
                {CATEGORIES.map((c) => (
                  <li key={c.key}>
                    <i className={`cat-${c.key}`} />
                    <b>
                      {c.name}
                      {c.scope && ` (${c.scope})`}
                    </b>{' '}
                    — {c.impact}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>
        <section className="panel">
          <div className="oh-ph">
            <h2>노드별 현황</h2>
            <p>최근 {WINDOW_DAYS}일 · 노드 이름을 누르면 그 노드 사건만 봅니다</p>
          </div>
          <div className="table-wrap">
            <table className="oh-table">
              <thead>
                <tr>
                  <th scope="col">노드</th>
                  <th scope="col">사건</th>
                  {CATEGORIES.map((c) => (
                    <th scope="col" key={c.key}>
                      {c.name}
                    </th>
                  ))}
                  <th scope="col">오류 난 장치</th>
                  <th scope="col">발생 중</th>
                  <th scope="col">확인 필요</th>
                  <th scope="col">마지막 사건</th>
                </tr>
              </thead>
              <tbody>
                {nodeStats(views).map((n) => (
                  <tr key={n.node}>
                    <td>
                      <Link className="text-link" to={`/cases?node=${encodeURIComponent(n.node)}`}>
                        {n.node}
                      </Link>
                    </td>
                    <td className="n">{n.total}</td>
                    {CATEGORIES.map((c) => (
                      <td className="n" key={c.key}>
                        {n.counts[c.key]}
                      </td>
                    ))}
                    <td className="n">{n.devices}</td>
                    <td className={`n ${n.firing ? 'oh-red' : ''}`}>{n.firing}</td>
                    <td className={`n ${n.stale ? 'oh-hot' : ''}`}>{n.stale}</td>
                    <td className="n">{dateTime(n.last)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>
      <section className="panel oh-foot" aria-label="내부 서비스 상태">
        {(
          [
            ['incident', '사건·알림 수신'],
            ['job_controller', 'RCA 실행 (Job Controller)'],
          ] as const
        ).map(([module, label]) => {
          const s = status(module);
          return (
            <span key={module}>
              <i className={`dot ${s === 'available' ? 'ok' : s === 'unavailable' ? 'bad' : ''}`} />
              <b>{label}</b>{' '}
              {s === 'available' ? '응답 정상' : s === 'unavailable' ? '응답 확인 실패' : '미확인'}
            </span>
          );
        })}
        {views[0] && <span>마지막 알림 {dateTime(views[0].at)}</span>}
        <Link className="text-link" to="/settings/backend">
          상태 상세
        </Link>
        <Link className="text-link" to="/reports">
          운영 분석 보고서
        </Link>
      </section>
    </div>
  );
}
