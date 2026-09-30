import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../lib/store';
import { queryPath, useList, useResource } from '../lib/live';
import { DataView, JobRows, More, QueryState } from '../components/live';
import { WorkflowGuide } from '../components/WorkflowGuide';
import { Notice } from '../components/ui';

export function DeveloperHome() {
  const app = useApp(),
    [kind, setKind] = useState('rca');
  const jobs = useList(
    app.canOperate ? queryPath('/jobs', { scope: app.scope, kind, limit: 12 }) : null,
    true,
  );
  const services = useResource(app.ready ? '/service-status' : null, undefined, true);
  return (
    <div className="page developer-page">
      <header className="dev-page-head">
        <div>
          <span className="dev-kicker">SYSTEM / DATA FLOW</span>
          <h1 tabIndex={-1}>처리 흐름과 검증 지점</h1>
          <p>단계를 선택해 확인할 데이터와 판단 기준을 읽고, 실제 작업으로 이동하세요.</p>
        </div>
        <Link className="button" to="/settings/backend">
          Backend 응답·서비스 상태
        </Link>
      </header>
      <div className="dev-pipeline-choice" role="group" aria-label="Agent 흐름 선택">
        <button aria-pressed={kind === 'rca'} onClick={() => setKind('rca')}>
          <b>RCA Agent</b>
          <span>Grafana → Incident → JC → RCA → 공개 결과</span>
        </button>
        <button aria-pressed={kind === 'report'} onClick={() => setKind('report')}>
          <b>보고서 Agent</b>
          <span>즉시 요청 / 정기 발생 → JC → Ops → 공개 결과</span>
        </button>
      </div>
      <WorkflowGuide key={kind} kind={kind} />
      <section className="panel">
        <div className="panel-head">
          <h2>실제 {kind === 'rca' ? 'RCA' : '보고서'} 작업 선택</h2>
          <Link to={`/jobs?kind=${kind}`} className="text-link">
            전체 실행 이력
          </Link>
        </div>
        <QueryState query={jobs} empty={!jobs.items.length}>
          <JobRows items={jobs.items} />
        </QueryState>
        <More query={jobs} />
      </section>
      <section className="panel live-padding stack">
        <h2>의존 서비스 응답</h2>
        <Notice>응답 정상은 Worker 실행·MCP 관측·LLM 분석 성공을 보장하지 않습니다.</Notice>
        <QueryState query={services}>
          <DataView value={services.data} />
        </QueryState>
      </section>
    </div>
  );
}
