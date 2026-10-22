import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { Badge, Field, PageHead, Panel } from '../components/ui';
import { AlarmIdentity, JobRows, More, QueryState } from '../components/live';
import { queryPath, str, useList } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
export function Cases() {
  const app = useApp();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'incidents' ? 'incidents' : 'analyses',
    status = params.get('status') ?? (params.get('tab') === 'reports' ? 'succeeded' : '');
  const setStatus = (value: string) => {
    const next = new URLSearchParams(params);
    next.set('tab', tab);
    next.set('status', value);
    setParams(next);
  };
  const q = useList(
    app.ready
      ? queryPath('/' + tab, {
          scope: app.scope,
          status,
          limit: 30,
        })
      : null,
    true,
  );
  return (
    <div className="page">
      <PageHead
        eyebrow=""
        title={app.mode === 'developer' ? '사건·RCA 연결' : 'RCA 조사'}
        description="진행 중인 조사와 완료된 결과를 한 목록에서 확인합니다. 완료된 제목을 선택하면 RCA 보고서로, 결과가 없으면 실행 이력으로 이동합니다."
        actions={
          app.mode === 'developer' ? (
            <Link className="button" to="/jobs?kind=rca">
              RCA 실행 작업 검색
            </Link>
          ) : undefined
        }
      />
      <div className="tabs">
        {[
          ['incidents', '사건'],
          ['analyses', 'RCA 조사'],
        ].map(([v, l]) => (
          <button
            className={tab === v ? 'active' : ''}
            key={v}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set('tab', v);
              next.delete('status');
              setParams(next);
            }}
          >
            {l}
          </button>
        ))}
      </div>
      <Panel title={tab === 'incidents' ? '사건 목록' : 'RCA 조사 목록'}>
        {
          <div className="live-toolbar">
            <Field label={tab === 'incidents' ? '사건 처리 상태' : '실행 상태'}>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">전체</option>
                {(tab === 'incidents'
                  ? ['open', 'acknowledged', 'closed']
                  : [
                      'queued',
                      'running',
                      'retry_wait',
                      'succeeded',
                      'failed',
                      'cancelled',
                      'expired',
                    ]
                ).map((s) => (
                  <option key={s} value={s}>
                    {s === 'succeeded' ? '분석 완료' : labels[s] || s}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        }
        <QueryState query={q} empty={!q.items.length}>
          {tab !== 'incidents' ? (
            <>
              <p className="muted">
                분석 완료는 원인 확정을 뜻하지 않습니다. 보고서에서 확인한 사실과 남은 제한을
                확인하세요.
              </p>
              <JobRows items={q.items} />
            </>
          ) : (
            <div className="table-wrap">
              <table className="incident-list">
                <thead>
                  <tr>
                    <th scope="col">알람 · 발생 대상</th>
                    <th scope="col">알람</th>
                    <th scope="col">사건</th>
                    <th scope="col">검토</th>
                    <th scope="col">발생 시각</th>
                  </tr>
                </thead>
                <tbody>
                  {q.items.map((i) => (
                    <tr key={str(i.id)}>
                      <td>
                        <Link
                          className="text-link"
                          to={`/incidents/${str(i.id)}`}
                          state={{ from: location.pathname + location.search }}
                        >
                          <AlarmIdentity record={i} />
                        </Link>
                        <small className="cell-sub">사건 ID · {str(i.id)}</small>
                      </td>
                      <td>
                        <Badge
                          status={str(i.alarm_status, 'unknown')}
                          label={
                            i.alarm_status === 'resolved'
                              ? '해제됨'
                              : i.alarm_status === 'firing'
                                ? '발생 중'
                                : undefined
                          }
                        />
                      </td>
                      <td>
                        <Badge status={str(i.state, str(i.status, 'unknown'))} />
                      </td>
                      <td>
                        <Badge status={str(i.review_status, 'unknown')} />
                      </td>
                      <td>{formatDate(str(i.occurred_at, str(i.created_at)))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
        <More query={q} />
      </Panel>
    </div>
  );
}
