import { dayKey, dayRange } from '../lib/incidentOverview';
import { str, type Row } from '../lib/live';
import { valueText, type MetricRow, type OperatorView, type Window } from '../lib/rcaOperatorView';
import { formatRcaTime } from '../lib/rcaTime';
import './rca-visual.css';

const clock = (value: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(value));
const validWindow = (w: Window | null): w is Window =>
  !!w &&
  w.samples > 0 &&
  [w.min, w.max, w.last].every(Number.isFinite) &&
  w.min <= w.last &&
  w.last <= w.max;

function MetricComparison({
  metric,
  target,
  onEvidence,
}: {
  metric: MetricRow;
  target: string;
  onEvidence?: (id: string) => void;
}) {
  const discrete = metric.kind === 'enum' || ['상태 코드', '비트마스크'].includes(metric.unit);
  const windows = metric.whole
    ? [{ label: '조회 구간 전체', value: metric.whole, text: metric.wholeText }]
    : [
        { label: '사건 전', value: metric.before, text: metric.beforeText },
        { label: '사건 후', value: metric.after, text: metric.afterText },
      ];
  const valid = windows.map((w) => w.value).filter(validWindow);
  const minimum = Math.min(...valid.map((w) => w.min));
  const maximum = Math.max(...valid.map((w) => w.max));
  const zoom = metric.kind === 'gauge' && metric.unit !== '%' && maximum > minimum;
  const padding = (maximum - minimum) * 0.1;
  const low = zoom
    ? Math.max(minimum >= 0 ? 0 : -Infinity, minimum - padding)
    : Math.min(0, ...valid.map((w) => w.min));
  const high = zoom
    ? maximum + padding
    : Math.max(metric.unit === '%' ? 100 : 1, ...valid.map((w) => w.max));
  const x = (value: number) => 12 + ((value - low) / (high - low)) * 276;
  return (
    <article className="c2-rca-metric">
      <h5>{metric.name}</h5>
      <p className="c2-rca-note">
        {target || '대상 식별 정보 없음'}
        {metric.kind === 'counter' && ' · 누적값'}
      </p>
      <div className="c2-rca-values">
        {windows.map(({ label, value, text }) => (
          <div key={label}>
            <span>{label}</span>
            <strong>
              {validWindow(value)
                ? discrete
                  ? text
                  : valueText(value.last, metric.unit)
                : '표본 없음·확인 불가'}
            </strong>
            {validWindow(value) && (
              <small>
                {discrete
                  ? ''
                  : `${valueText(value.min, metric.unit)} ~ ${valueText(value.max, metric.unit)} · `}
                {value.samples}개 표본
              </small>
            )}
          </div>
        ))}
      </div>
      {!discrete && valid.length > 0 && (
        <svg
          className="c2-rca-range"
          viewBox={`0 0 300 ${windows.length * 30 + 24}`}
          role="img"
          aria-label={`${metric.name}: 구간별 최솟값·최댓값 범위와 마지막 값`}
        >
          <title>
            {windows
              .map(
                ({ label, value }) =>
                  `${label}: ${validWindow(value) ? `${valueText(value.min, metric.unit)} ~ ${valueText(value.max, metric.unit)}, 마지막 ${valueText(value.last, metric.unit)}` : '표본 없음·확인 불가'}`,
              )
              .join('; ')}
          </title>
          {windows.map(({ label, value }, i) => (
            <g key={label}>
              <line x1="12" x2="288" y1={18 + i * 30} y2={18 + i * 30} stroke="#e5eae7" />
              {validWindow(value) && (
                <g fill={i === 0 ? '#72837a' : '#76a900'} stroke={i === 0 ? '#72837a' : '#76a900'}>
                  <line
                    x1={x(value.min)}
                    x2={x(value.max)}
                    y1={18 + i * 30}
                    y2={18 + i * 30}
                    strokeWidth="8"
                    strokeLinecap="round"
                  />
                  <circle
                    cx={x(value.last)}
                    cy={18 + i * 30}
                    r="5"
                    stroke="#fff"
                    strokeWidth="1.5"
                  />
                </g>
              )}
              <text x="12" y={9 + i * 30} fontSize="10" fill="#58675e">
                {label}
              </text>
            </g>
          ))}
          <text x="12" y={windows.length * 30 + 18} fontSize="11" fill="#58675e">
            {valueText(low, metric.unit)}
          </text>
          <text x="288" y={windows.length * 30 + 18} textAnchor="end" fontSize="11" fill="#58675e">
            {valueText(high, metric.unit)}
          </text>
        </svg>
      )}
      {zoom && <p className="c2-rca-note">작은 차이를 볼 수 있도록 관측 범위에 맞춘 축입니다.</p>}
      {metric.whole && <p className="c2-rca-note">사건 전후로 나뉘지 않은 저장값입니다.</p>}
      {metric.kind === 'counter' && (
        <p className="c2-rca-note">누적값의 크기는 이번 사건의 발생 건수가 아닙니다.</p>
      )}
      <div className="c2-rca-evidence">
        {onEvidence &&
          [...new Set(metric.refs)].map((id, i) => (
            <button key={id} className="text-link" onClick={() => onEvidence(id)}>
              근거 원문{metric.refs.length > 1 ? ` ${i + 1}` : ''}
            </button>
          ))}
      </div>
    </article>
  );
}

export function RcaVisualEvidence({
  view: v,
  onEvidence,
}: {
  view: OperatorView;
  onEvidence?: (id: string) => void;
}) {
  const start = Date.parse(v.periodStart),
    end = Date.parse(v.periodEnd);
  const hasPeriod = Number.isFinite(start) && Number.isFinite(end) && end > start;
  const events = [
    { label: v.eventLabel || '커널 원본 이벤트', at: v.eventTime },
    { label: '첫 오류 로그 기록', at: v.firstReport },
    { label: '마지막 오류 로그 기록', at: v.lastReport },
    { label: '지표 비교 기준', at: v.boundary },
  ];
  const x = (at: string) => 190 + ((Date.parse(at) - start) / (end - start)) * 420;
  const inside = (at: string) => hasPeriod && Date.parse(at) >= start && Date.parse(at) <= end;
  return (
    <section id="c2-rca-visual" className="c2-rca-visual" aria-label="RCA 관측 비교">
      <h4>관측 비교</h4>
      <div className="c2-rca-time">
        <header>
          <h5>오류 기록과 지표의 시각 대조</h5>
          <a href="#rca-observation-detail">로그·지표 상세 ↓</a>
        </header>
        <p className="c2-rca-note">
          {v.codes.join(', ')} · {v.node}
          {v.alertPci && ` · PCI ${v.alertPci}`} · 점은 저장된 시각입니다. 점 사이를 장애 지속
          시간으로 해석하지 않습니다.
        </p>
        {hasPeriod ? (
          <div className="c2-rca-chart-scroll">
            <svg
              className="c2-rca-timeline"
              viewBox="0 0 960 224"
              role="img"
              aria-label="오류 기록과 지표 비교 기준 시각, 한국 시간"
            >
              <title>{events.map((e) => `${e.label}: ${formatRcaTime(e.at)}`).join('; ')}</title>
              {[0, 1, 2, 3, 4].map((n) => (
                <g key={n}>
                  <line
                    x1={190 + n * 105}
                    x2={190 + n * 105}
                    y1="30"
                    y2="184"
                    stroke="#e1e7e3"
                    strokeDasharray="3 4"
                  />
                  <text x={190 + n * 105} y="211" textAnchor="middle" fontSize="12" fill="#58675e">
                    {clock(new Date(start + ((end - start) * n) / 4).toISOString())}
                  </text>
                </g>
              ))}
              {inside(v.boundary) && (
                <line
                  x1={x(v.boundary)}
                  x2={x(v.boundary)}
                  y1="27"
                  y2="184"
                  stroke="#7a942f"
                  strokeDasharray="4 4"
                />
              )}
              {events.map((event, i) => (
                <g key={event.label}>
                  <text x="6" y={49 + i * 40} fontSize="13" fill="#283c30">
                    {event.label}
                  </text>
                  <line x1="190" x2="610" y1={44 + i * 40} y2={44 + i * 40} stroke="#dce4de" />
                  {inside(event.at) && (
                    <circle
                      cx={x(event.at)}
                      cy={44 + i * 40}
                      r="6"
                      fill={i === 3 ? '#76a900' : '#397fc2'}
                    />
                  )}
                  <text x="638" y={49 + i * 40} fontSize="12" fill="#283c30">
                    {Number.isFinite(Date.parse(event.at))
                      ? `${formatRcaTime(event.at)}${inside(event.at) ? '' : ' · 구간 밖'}`
                      : '시각 미기록'}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        ) : (
          <dl className="c2-rca-time-list">
            {events.map((event) => (
              <div key={event.label}>
                <dt>{event.label}</dt>
                <dd>
                  {Number.isFinite(Date.parse(event.at)) ? formatRcaTime(event.at) : '시각 미기록'}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <p className="c2-rca-note">
          조회 구간: {formatRcaTime(v.periodStart)} ~ {formatRcaTime(v.periodEnd)}
          {!hasPeriod && ' · 유효한 조회 구간이 없어 시간축을 표시하지 않습니다.'}
        </p>
      </div>
      <header className="c2-rca-metrics-heading">
        <h5>사건 전후 지표 비교</h5>
        <span>선: 최솟값~최댓값 · 점: 마지막 값</span>
      </header>
      <p className="c2-rca-note">
        저장된 구간 집계입니다. 시간에 따른 변화 곡선이나 원인 확정을 뜻하지 않습니다. 표본 수가
        적은 구간은 상세 근거를 함께 확인하세요.
      </p>
      {v.metrics.length ? (
        <div className="c2-rca-metrics">
          {v.metrics.map((metric, i) => (
            <MetricComparison
              key={i}
              metric={metric}
              target={v.gpuSet(metric.uuids)}
              onEvidence={onEvidence}
            />
          ))}
        </div>
      ) : (
        <p className="c2-rca-empty">
          비교할 지표가 저장되지 않았습니다. 아래 로그와 분석 근거를 확인하세요.
        </p>
      )}
    </section>
  );
}

export function RcaHistoryChart({
  incidents,
  start,
  end,
  complete,
}: {
  incidents: Row[];
  start: number;
  end: number;
  complete: boolean;
}) {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const days = dayRange(dayKey(new Date(start)), dayKey(new Date(end)));
  const unique = [
    ...new Map(
      incidents
        .filter(
          (r) =>
            str(r.incident_id) &&
            Date.parse(str(r.occurred_at)) >= start &&
            Date.parse(str(r.occurred_at)) <= end,
        )
        .map((r) => [str(r.incident_id), r]),
    ).values(),
  ];
  const counts = days.map(
    (day) => unique.filter((r) => dayKey(new Date(str(r.occurred_at))) === day).length,
  );
  const peak = Math.max(1, ...counts),
    step = 820 / days.length;
  return (
    <div className="c2-rca-history-chart">
      <header>
        <h5>날짜별 등록 사건</h5>
        <span>선택 조건 {unique.length}건 · KST</span>
      </header>
      <p className="c2-rca-note">
        위 필터와 같은 조건 · Incident ID별 집계 · 첫날과 마지막 날은 조회 시간에 포함된 사건만 표시
        {!complete && ' · 일부 이력만 저장된 결과입니다.'}
      </p>
      <div className="c2-rca-chart-scroll">
        <svg
          viewBox="0 0 900 200"
          role="img"
          aria-label={`선택 조건의 날짜별 등록 사건 ${unique.length}건`}
        >
          <title>{days.map((day, i) => `${day}: ${counts[i]}건`).join('; ')}</title>
          {[0, 1, 2].map((n) => (
            <g key={n}>
              <line
                x1="46"
                x2="874"
                y1={156 - n * 60}
                y2={156 - n * 60}
                stroke="#dce4de"
                strokeDasharray={n ? '3 4' : undefined}
              />
              <text x="36" y={161 - n * 60} textAnchor="end" fontSize="12" fill="#58675e">
                {Math.ceil(peak / 2) * n}
              </text>
            </g>
          ))}
          {days.map((day, i) => {
            const h = (counts[i] / (Math.ceil(peak / 2) * 2)) * 120;
            const x = 50 + (i + 0.5) * step;
            return (
              <g key={day}>
                <title>{`${day} · ${counts[i]}건`}</title>
                <rect
                  x={x - step * 0.27}
                  width={step * 0.54}
                  y={156 - h}
                  height={h}
                  rx="3"
                  fill="#76a900"
                />
                <text x={x} y={148 - h} textAnchor="middle" fontSize="12" fill="#283c30">
                  {counts[i]}
                </text>
                <text x={x} y="183" textAnchor="middle" fontSize="11" fill="#58675e">
                  {day.slice(5).replace('-', '.')}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
