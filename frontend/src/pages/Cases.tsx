import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom';
import { Badge, Field, PageHead, Panel } from '../components/ui';
import { AlarmIdentity, JobRows, More, QueryState } from '../components/live';
import { queryPath, str, useList } from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
export function Cases() {
  const app = useApp();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const tab = ['analyses', 'reports'].includes(params.get('tab') || '')
      ? params.get('tab')!
      : 'incidents',
    status = params.get('status') || '';
  const setStatus = (value: string) => {
    const next = new URLSearchParams(params);
    next.set('status', value);
    setParams(next);
  };
  const q = useList(
    app.ready && !(app.mode === 'developer' && tab !== 'incidents')
      ? queryPath('/' + (tab === 'reports' ? 'analyses' : tab), {
          scope: app.scope,
          status: tab === 'reports' ? 'succeeded' : status,
          limit: 30,
        })
      : null,
    true,
  );
  if (app.mode === 'developer' && tab !== 'incidents') {
    return (
      <Navigate
        replace
        to={`/jobs?kind=rca${tab === 'reports' ? '&status=succeeded' : status ? `&status=${encodeURIComponent(status)}` : ''}`}
      />
    );
  }
  return (
    <div className="page">
      <PageHead
        eyebrow="ROOT CAUSE ANALYSIS"
        title={app.mode === 'developer' ? '사건·RCA 연결' : 'RCA 조사'}
        description="사건에 연결된 RCA 조사와 발행된 결과를 확인합니다."
        actions={
          app.mode === 'developer' ? (
            <Link className="button" to="/jobs?kind=rca">
              RCA 실행 작업 검색
            </Link>
          ) : (
            <Link className="button primary" to="/cases?tab=reports">
              최종 보고서
            </Link>
          )
        }
      />
      {app.mode !== 'developer' && (
        <div className="tabs">
          {[
            ['incidents', '사건'],
            ['analyses', '조사 이력'],
            ['reports', '최종 보고서'],
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
      )}
      <Panel
        title={
          tab === 'incidents' ? '사건 목록' : tab === 'reports' ? '공개된 RCA 보고서' : '조사 목록'
        }
      >
        {tab !== 'reports' && (
          <div className="live-toolbar">
            <Field label={tab === 'incidents' ? '사건 처리 상태' : '실행 상태'}>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">전체</option>
                {(tab === 'incidents'
                  ? ['open', 'acknowledged', 'closed']
                  : ['queued', 'running', 'succeeded', 'failed', 'cancelled']
                ).map((s) => (
                  <option key={s} value={s}>
                    {labels[s] || s}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        <QueryState query={q} empty={!q.items.length}>
          {tab !== 'incidents' ? (
            <JobRows items={q.items} preferResult={tab === 'reports'} />
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
