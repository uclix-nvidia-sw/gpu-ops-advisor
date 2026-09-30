import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Field, PageHead, Panel } from '../components/ui';
import { AlarmIdentity, JobRows, More, QueryState } from '../components/live';
import { queryPath, str, useList } from '../lib/live';
import { IncidentStates } from '../components/RcaDebug';
import { formatDate, labels } from '../lib/domain';
import { useApp } from '../lib/store';
export function Cases() {
  const app = useApp();
  const [tab, setTab] = useState('incidents'),
    [status, setStatus] = useState('');
  const q = useList(
    app.ready ? queryPath('/' + tab, { scope: app.scope, status, limit: 30 }) : null,
    true,
  );
  return (
    <div className="page">
      <PageHead
        eyebrow="ROOT CAUSE ANALYSIS"
        title="RCA 조사"
        description="사건에 연결된 RCA 조사와 발행된 결과를 확인합니다."
      />
      <div className="tabs">
        {[
          ['incidents', '사건'],
          ['analyses', '조사 이력'],
        ].map(([v, l]) => (
          <button
            className={tab === v ? 'active' : ''}
            key={v}
            onClick={() => {
              setTab(v);
              setStatus('');
            }}
          >
            {l}
          </button>
        ))}
      </div>
      <Panel title={tab === 'incidents' ? '사건 목록' : '조사 목록'}>
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
        <QueryState query={q} empty={!q.items.length}>
          {tab === 'analyses' ? (
            <JobRows items={q.items} />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>알람 · 발생 대상</th>
                    <th>알람·사건·검토 상태</th>
                    <th>발생 시각</th>
                  </tr>
                </thead>
                <tbody>
                  {q.items.map((i) => (
                    <tr key={str(i.id)}>
                      <td>
                        <Link className="text-link" to={`/incidents/${str(i.id)}`}>
                          <AlarmIdentity record={i} />
                        </Link>
                        <small className="cell-sub">사건 ID · {str(i.id)}</small>
                      </td>
                      <td>
                        <IncidentStates incident={i} />
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
