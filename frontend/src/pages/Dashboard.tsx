import { Link } from 'react-router-dom';
import { Activity, ArrowUpRight, Database, ScanSearch } from 'lucide-react';
import { Badge, PageHead, Panel } from '../components/ui';
import { DataView, JobRows, QueryState } from '../components/live';
import { obj, queryPath, rows, str, useList, useResource } from '../lib/live';
import { useApp } from '../lib/store';
export function Dashboard() {
  const app = useApp();
  const q = useResource(
      app.ready
        ? queryPath('/dashboard', {
            scope: app.scope,
            time_range: app.timeRange,
            timezone: 'Asia/Seoul',
          })
        : null,
    ),
    jobs = useList(app.ready ? queryPath('/jobs', { scope: app.scope, limit: 5 }) : null, true),
    modules = useResource('/service-status');
  const data = q.data || {};
  return (
    <div className="page">
      <PageHead
        eyebrow="OPERATIONS OVERVIEW"
        title="운영 대시보드"
        description="선택한 범위의 실제 관측과 작업 상태를 확인합니다."
        actions={
          <Link className="button primary" to="/cases">
            <ScanSearch size={16} />
            사건·조사 보기
          </Link>
        }
      />
      <QueryState query={q}>
        <div className="live-metrics">
          <div className="panel metric-card">
            <Activity size={21} />
            <span>관측 품질</span>
            <strong>
              <Badge status={str(data.tool_status, 'unknown')} />
            </strong>
            <small>서버가 보고한 수집 상태</small>
          </div>
          <div className="panel metric-card">
            <ScanSearch size={21} />
            <span>등록된 사건</span>
            <strong>{typeof data.incident_count === 'number' ? data.incident_count : '—'}</strong>
            <small>선택 범위·기간</small>
          </div>
          <div className="panel metric-card">
            <Database size={21} />
            <span>GPU 할당</span>
            <strong>{data.allocation_summary ? '조회됨' : '미확인'}</strong>
            <small>미수집 값은 0으로 표시하지 않습니다.</small>
          </div>
        </div>
        <Panel title="수집 상태와 품질" description="관측 데이터의 출처와 가용성을 확인하세요.">
          <div className="live-padding">
            <DataView value={data.quality} />
            {data.allocation_summary != null && <DataView value={data.allocation_summary} />}
          </div>
        </Panel>
      </QueryState>
      <div className="live-two-columns">
        <Panel
          title="최근 작업"
          action={
            <Link className="text-link" to="/jobs">
              전체 보기
              <ArrowUpRight size={14} />
            </Link>
          }
        >
          <QueryState query={jobs} empty={!jobs.items.length}>
            <JobRows items={jobs.items} />
          </QueryState>
        </Panel>
        <Panel
          title="서비스 연결"
          action={
            <Link className="text-link" to="/settings/backend">
              연결 상세
            </Link>
          }
        >
          <QueryState query={modules}>
            <div className="backend-modules">
              {rows(modules.data?.items).map((m) => (
                <div className="backend-module" key={str(m.module)}>
                  <strong>
                    {(
                      {
                        job_controller: 'Job Controller',
                        incident: '사건·알림',
                      } as Record<string, string>
                    )[str(m.module)] || str(m.module)}
                  </strong>
                  <Badge status={str(m.status)} />
                </div>
              ))}
            </div>
            {obj(modules.data?.database).status != null && (
              <DataView value={modules.data?.database} />
            )}
          </QueryState>
        </Panel>
      </div>
    </div>
  );
}
