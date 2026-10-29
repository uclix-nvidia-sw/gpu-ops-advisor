import { useState } from 'react';
import { Link } from 'react-router-dom';
import { QueryState } from '../components/live';
import {
  CodeBadge,
  DeviceText,
  ErrorTitle,
  RcaLink,
  RepeatBadge,
  WINDOW_DAYS,
  useRecentIncidents,
} from '../components/IncidentOverview';
import { OpsUsage } from '../components/OpsUsage';
import { rows, str, useResource } from '../lib/live';
import {
  CATEGORIES,
  ago,
  category,
  categorySummary,
  dailyCounts,
  dateTimeText,
  dayKey,
  deviceRepeats,
  errorRepeats,
  kindText,
  nodeStats,
  shortDate,
  windowDays,
  type Category,
  type IncidentView,
} from '../lib/incidentOverview';

const PLOT = 170;

function counts(views: IncidentView[]) {
  return Object.fromEntries(
    CATEGORIES.map((c) => [c.key, views.filter((v) => category(v) === c.key).length]),
  ) as Record<Category, number>;
}

/** Ring chart of category counts with the total in the middle. */
function Donut({ values, title }: { values: Record<Category, number>; title: string }) {
  const total = Object.values(values).reduce((a, b) => a + b, 0);
  const R = 49;
  const length = 2 * Math.PI * R;
  let offset = 0;
  return (
    <figure className="oh-donut">
      <svg viewBox="0 0 150 150" role="img" aria-label={`${title} ${total}건`}>
        <circle cx="75" cy="75" r={R} className="oh-ring" />
        {CATEGORIES.filter((c) => values[c.key]).map((c) => {
          const part = (values[c.key] / total) * length;
          const arc = (
            <circle
              key={c.key}
              cx="75"
              cy="75"
              r={R}
              className={`oh-arc cat-${c.key}`}
              strokeDasharray={`${part} ${length - part}`}
              strokeDashoffset={-offset}
            >
              <title>{`${c.name} ${values[c.key]}건`}</title>
            </circle>
          );
          offset += part;
          return arc;
        })}
        <text x="75" y="73" className="oh-donut-n">
          {total}
        </text>
        <text x="75" y="93" className="oh-donut-u">
          건
        </text>
      </svg>
      <figcaption>{title}</figcaption>
    </figure>
  );
}

/** Classic-mode dashboard: received alert states, how faults split and where they repeat. */
export function OperatorDashboard() {
  const { query, views, now, truncated } = useRecentIncidents();
  const modules = useResource('/service-status');
  const [repeatBy, setRepeatBy] = useState<'device' | 'error' | 'time'>('device');
  const [expandIncidents, setExpandIncidents] = useState(false);
  const days = windowDays(now, WINDOW_DAYS);
  const today = dayKey(now);
  const firing = views.filter((v) => v.firing);
  const resolved = views.filter((v) => v.resolved);
  const todays = views.filter((v) => dayKey(v.at) === today);
  const repeats = deviceRepeats(views, days);
  const hot = repeats.filter((d) => d.count >= 3);
  const daily = dailyCounts(views, days);
  const dayTotal = (d: (typeof daily)[number]) =>
    Object.values(d.counts).reduce((a, b) => a + b, 0);
  const yTop = Math.max(5, Math.ceil(Math.max(...daily.map(dayTotal), 1) / 5) * 5);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yTop * f));
  const todayCounts = counts(todays);
  const windowCounts = counts(views);
  const maxDevice = Math.max(...repeats.map((d) => d.count), 1);
  const byError = errorRepeats(views);
  const maxError = Math.max(...byError.map((e) => e.count), 1);
  const deviceRows =
    repeatBy === 'time'
      ? [...repeats].sort((a, b) => b.last.getTime() - a.last.getTime())
      : repeats;
  const status = (module: string) =>
    str(rows(modules.data?.items).find((m) => m.module === module)?.status);
  return (
    <div className="page oh-page">
      <div className="oh-head-row">
        <div>
          <div className="oh-eyebrow">GPU OPERATIONS</div>
          <h1 tabIndex={-1}>운영 대시보드</h1>
          <p className="oh-sub">
            GPU 서버 장애 현황 · 최근 {WINDOW_DAYS}일 · 기준 {dateTimeText(now)} KST
          </p>
        </div>
        <Link className="oh-btn" to="/cases">
          RCA 조사 보기 →
        </Link>
      </div>
      <OpsUsage />
      <QueryState query={query}>
        {truncated && (
          <p className="muted">
            사건이 많아 최근 일부만 집계했습니다. 사건 화면에서 범위를 좁혀 확인하세요.
          </p>
        )}
        <div className="oh-kpis">
          <Link className="oh-kpi" to={`/cases?focus=firing&period=${WINDOW_DAYS}`}>
            <span>
              <i className="oh-dot red" />
              발생 알림 수신
            </span>
            <strong>{firing.length}</strong>
            <small>발생 알림 기록 · 현재 상태는 별도 확인</small>
          </Link>
          <Link className="oh-kpi" to={`/cases?focus=resolved&period=${WINDOW_DAYS}`}>
            <span>
              <i className="oh-dot" />
              해제 알림 수신
            </span>
            <strong>{resolved.length}</strong>
            <small>과거 해제 알림 기록 · 복구 확정 아님</small>
          </Link>
          <Link className="oh-kpi" to="/cases?focus=today&period=1">
            <span>
              <i className="oh-dot green" />
              오늘 사건
            </span>
            <strong>{todays.length}</strong>
            <small>{categorySummary(todays) || '오늘 사건 없음'}</small>
          </Link>
          <Link className="oh-kpi" to={`/cases?sort=device&period=${WINDOW_DAYS}`}>
            <span>
              <i className="oh-dot" />
              반복 장치 ({WINDOW_DAYS}일 3회 이상)
            </span>
            <strong>{hot.length}</strong>
            <small>공급사 전달 검토 대상</small>
          </Link>
        </div>
        <div className="oh-grid">
          <section className="oh-card">
            <div className="oh-card-h">
              <div>
                <h2>장애 구성</h2>
                <p>분류별 건수 — 오늘과 최근 {WINDOW_DAYS}일</p>
              </div>
            </div>
            <div className="oh-card-b">
              <div className="oh-donuts">
                <Donut values={todayCounts} title="오늘" />
                <Donut values={windowCounts} title={`최근 ${WINDOW_DAYS}일`} />
              </div>
              <table className="oh-legend">
                <thead>
                  <tr>
                    <th scope="col">분류</th>
                    <th scope="col">오늘</th>
                    <th scope="col">{WINDOW_DAYS}일</th>
                  </tr>
                </thead>
                <tbody>
                  {CATEGORIES.map((c) => (
                    <tr key={c.key}>
                      <td>
                        <i className={`cat-${c.key}`} />
                        <b>
                          {c.name}
                          {c.scope && ` (${c.scope})`}
                        </b>
                        <small>{c.impact}</small>
                      </td>
                      <td className="n">{todayCounts[c.key]}건</td>
                      <td className="n">{windowCounts[c.key]}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="oh-card">
            <div className="oh-card-h">
              <div>
                <h2>최근 {WINDOW_DAYS}일 사건 추이</h2>
                <p>하루 단위 사건 수 · 막대 위 숫자는 그날 합계</p>
              </div>
            </div>
            <div className="oh-card-b">
              <div className="oh-unit">단위: 건/일</div>
              <div className="oh-chart">
                <div className="oh-yax" aria-hidden="true">
                  {ticks.map((t) => (
                    <span key={t} style={{ top: PLOT - (t / yTop) * PLOT }}>
                      {t}
                    </span>
                  ))}
                </div>
                <div className="oh-plot" role="img" aria-label="날짜별 사건 수">
                  {ticks.slice(1).map((t) => (
                    <div className="g" key={t} style={{ top: PLOT - (t / yTop) * PLOT }} />
                  ))}
                  {daily.map((d) => (
                    <div
                      className="c"
                      key={d.day}
                      title={`${shortDate(d.day)} · ${CATEGORIES.map((c) => `${c.name} ${d.counts[c.key]}건`).join(' · ')}`}
                    >
                      {CATEGORIES.map((c) =>
                        d.counts[c.key] ? (
                          <i
                            key={c.key}
                            className={`cat-${c.key}`}
                            style={{ height: (d.counts[c.key] / yTop) * PLOT }}
                          />
                        ) : null,
                      )}
                      {dayTotal(d) > 0 && <b>{dayTotal(d)}</b>}
                    </div>
                  ))}
                </div>
              </div>
              <div className="oh-xl">
                {daily.map((d) => (
                  <span key={d.day} className={d.day === today ? 'today' : ''}>
                    {shortDate(d.day).slice(0, 5)}
                    <br />
                    {shortDate(d.day).slice(6)}
                  </span>
                ))}
              </div>
            </div>
          </section>
        </div>
        <section className="oh-card">
          <div className="oh-card-h">
            <div>
              <h2>발생 알림이 수신된 사건</h2>
              <p>
                수신 기록으로 현재 장애 지속·복구 여부를 판단하지 않습니다. 대응 순서와 근거는 RCA
                보고서에서 확인합니다.
              </p>
            </div>
            <button
              className="text-link"
              aria-expanded={expandIncidents}
              aria-controls="received-incidents"
              onClick={() => setExpandIncidents(!expandIncidents)}
            >
              {expandIncidents ? '높이 제한으로 보기' : '전체 펼치기'}
            </button>
          </div>
          <div
            id="received-incidents"
            className={`oh-card-b oh-received-incidents${expandIncidents ? ' is-expanded' : ''}`}
            role="region"
            aria-label="발생 알림이 수신된 사건 목록"
            tabIndex={0}
          >
            {firing.length ? (
              firing.map((v) => (
                <article className="oh-now" key={v.id}>
                  <div>
                    <h3>
                      <ErrorTitle v={v} />
                    </h3>
                    <div className="meta">
                      <DeviceText v={v} /> · {ago(v.at, now)} 전 시작 ({dateTimeText(v.at)}){' '}
                      <RepeatBadge v={v} />
                    </div>
                    <div className="act">
                      NVIDIA 즉시 조치 분류: <b>{v.label?.action || '런북 순서대로 확인'}</b>
                    </div>
                  </div>
                  <div className="oh-actions">
                    <RcaLink v={v} button />
                    {v.kind !== 'host' && (
                      <Link
                        className="oh-btn line"
                        to={`/cases?device=${encodeURIComponent(v.deviceKey)}&period=${WINDOW_DAYS}`}
                      >
                        이 {kindText(v.kind)} 사건 이력
                      </Link>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <p className="muted">조회 기간에 발생 알림 수신으로 기록된 사건이 없습니다.</p>
            )}
          </div>
        </section>
        <section className="oh-card">
          <div className="oh-card-h">
            <div>
              <h2>반복 장치</h2>
              <p>최근 {WINDOW_DAYS}일 같은 장치·같은 오류. 3회 이상은 공급사 전달을 검토합니다.</p>
            </div>
            <span className="oh-seg">
              {(
                [
                  ['device', '장치별'],
                  ['error', '에러별'],
                  ['time', '시간별'],
                ] as const
              ).map(([key, label]) => (
                <button key={key} aria-pressed={repeatBy === key} onClick={() => setRepeatBy(key)}>
                  {label}
                </button>
              ))}
            </span>
          </div>
          <div className="oh-card-b oh-bars">
            {repeatBy === 'error'
              ? byError.map((e) => (
                  <Link className="b" key={e.code} to={`/cases?sort=error&period=${WINDOW_DAYS}`}>
                    <span>
                      <CodeBadge code={e.code} text={e.codeText} /> <b>{e.name}</b>{' '}
                      <small>
                        · 장치 {e.devices}개 · 마지막 {dateTimeText(e.last)}
                      </small>
                    </span>
                    <span
                      className={`bar ${e.kind}`}
                      style={{ width: `${(e.count / maxError) * 100}%` }}
                    />
                    <b className="n">{e.count}회</b>
                  </Link>
                ))
              : deviceRows.slice(0, 10).map((d) => (
                  <Link
                    className="b"
                    key={d.key}
                    to={`/cases?device=${encodeURIComponent(d.key)}&period=${WINDOW_DAYS}`}
                  >
                    <span>
                      <b>{d.node}</b> {kindText(d.kind)} <code className="oh-code">{d.device}</code>{' '}
                      <CodeBadge code={d.code} text={d.codeText} />{' '}
                      <small>· 마지막 {dateTimeText(d.last)}</small>
                    </span>
                    <span
                      className={`bar ${d.kind}`}
                      style={{ width: `${(d.count / maxDevice) * 100}%` }}
                    />
                    <b className="n">{d.count}회</b>
                  </Link>
                ))}
            {!repeats.length && <p className="muted">반복된 장치가 없습니다.</p>}
          </div>
        </section>
        <section className="oh-card">
          <div className="oh-card-h">
            <div>
              <h2>노드별 현황</h2>
              <p>최근 {WINDOW_DAYS}일 · 노드 이름을 누르면 그 노드 사건만 봅니다</p>
            </div>
          </div>
          <div className="oh-card-b table-wrap">
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
                  <th scope="col">발생 알림 수신</th>
                  <th scope="col">해제 알림 수신</th>
                  <th scope="col">마지막 사건</th>
                </tr>
              </thead>
              <tbody>
                {nodeStats(views).map((n) => (
                  <tr key={n.node}>
                    <td>
                      <Link
                        className="oh-node"
                        to={`/cases?node=${encodeURIComponent(n.node)}&period=${WINDOW_DAYS}`}
                      >
                        {n.node}
                      </Link>
                    </td>
                    <td>
                      <b>{n.total}</b>
                    </td>
                    {CATEGORIES.map((c) => (
                      <td key={c.key}>{n.counts[c.key]}</td>
                    ))}
                    <td>{n.devices}</td>
                    <td>
                      {n.firing ? (
                        <b>
                          <i className="oh-dot red" />
                          {n.firing}
                        </b>
                      ) : (
                        0
                      )}
                    </td>
                    <td>
                      {n.resolved ? (
                        <b>
                          <i className="oh-dot" />
                          {n.resolved}
                        </b>
                      ) : (
                        0
                      )}
                    </td>
                    <td>{dateTimeText(n.last)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>
      <section className="oh-card oh-foot" aria-label="내부 서비스 상태">
        {(
          [
            ['incident', '사건·알림 수신'],
            ['job_controller', 'RCA 실행 (Job Controller)'],
          ] as const
        ).map(([module, label]) => {
          const s = status(module);
          return (
            <span key={module}>
              <i
                className={`oh-dot ${s === 'available' ? 'green' : s === 'unavailable' ? 'red' : ''}`}
              />
              <b>{label}</b>{' '}
              {s === 'available' ? '응답 정상' : s === 'unavailable' ? '응답 확인 실패' : '미확인'}
            </span>
          );
        })}
        {views[0] && <span>마지막 알림 {dateTimeText(views[0].at)}</span>}
        <Link to="/settings/backend">상태 상세</Link>
        <Link to="/reports">운영 분석 보고서</Link>
      </section>
    </div>
  );
}
