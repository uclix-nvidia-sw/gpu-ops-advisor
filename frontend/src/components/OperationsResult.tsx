import { Link } from 'react-router-dom';
import { rows, str, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';
import { AlarmIdentity, DataView } from './live';
import { IncidentStates } from './RcaDebug';
import { Badge, Notice } from './ui';

export function OperationsIncident({ incident }: { incident: Row }) {
  return (
    <div className="ops-incident">
      <header>
        <AlarmIdentity record={incident} />
        <IncidentStates incident={incident} />
      </header>
      <div className="ops-incident-grid">
        <section>
          <h3>무엇이 들어왔나요?</h3>
          <p>{str(incident.symptom, str(incident.title, '증상 설명이 제공되지 않았습니다.'))}</p>
          <dl className="details">
            <dt>처음 수신</dt>
            <dd>{formatDate(str(incident.episode_started_at, str(incident.occurred_at)))}</dd>
            <dt>최근 수신</dt>
            <dd>{formatDate(str(incident.last_observed_at))}</dd>
            <dt>수신 횟수</dt>
            <dd>
              {typeof incident.observation_count === 'number'
                ? incident.observation_count
                : '미확인'}
            </dd>
            <dt>관측 종료</dt>
            <dd>{formatDate(str(incident.ended_at))}</dd>
            <dt>사건 종결</dt>
            <dd>{formatDate(str(incident.closed_at))}</dd>
          </dl>
          {incident.prior_incident_id != null && (
            <Link className="text-link" to={`/incidents/${str(incident.prior_incident_id)}`}>
              이전 사건 확인
            </Link>
          )}
        </section>
        <section>
          <h3>분석을 확인하세요</h3>
          {rows(incident.analyses).length ? (
            rows(incident.analyses).map((a) => (
              <Link
                className="ops-analysis-link"
                key={str(a.job_id)}
                to={`/analyses/${str(a.job_id)}`}
              >
                <div>
                  <b>연결된 RCA 분석</b>
                  <small>{str(a.job_id)}</small>
                </div>
                <Badge status={str(a.status, 'unknown')} />
                <span>결과 확인 →</span>
              </Link>
            ))
          ) : (
            <Notice>연결된 RCA 작업이 없습니다. 분석 접수 여부와 알람 연결을 확인하세요.</Notice>
          )}
          {incident.rca_eligibility_reason != null && (
            <p>접수 판단 사유: {str(incident.rca_eligibility_reason)}</p>
          )}
          <p className="muted">알람이 해제되어도 원인과 복구 여부는 별도로 확인해야 합니다.</p>
        </section>
      </div>
      <details>
        <summary>사건 원본·대상 정보</summary>
        <DataView value={incident} explain />
      </details>
    </div>
  );
}
