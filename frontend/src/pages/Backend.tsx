import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Database, RefreshCw, Server, Unplug } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { apiRequest, ApiError } from '../lib/api';

type Health = { status: string; request_id: string };
type Module = { module: string; status: string };
const moduleLabels: Record<string, string> = {
  job_controller: 'Job Controller',
  incident: '사건·알림',
};
const message = (error: unknown) =>
  error instanceof ApiError
    ? `${error.message}${error.requestId ? ` · 요청 ${error.requestId}` : ''}`
    : '백엔드에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.';

export function Backend() {
  const client = useQueryClient();
  const health = useQuery({
    queryKey: ['api', 'health'],
    queryFn: () => apiRequest<Health>('/health/ready'),
    retry: false,
  });
  const modules = useQuery({
    queryKey: ['api', 'modules'],
    queryFn: () => apiRequest<{ items: Module[] }>('/service-status'),
    retry: false,
  });
  return (
    <div className="page backend-page">
      <PageHead
        eyebrow="BACKEND CONNECTION"
        title="백엔드 연결"
        description="Go API와 PostgreSQL의 실제 연결 상태 및 저장 결과를 확인합니다."
        actions={
          <button
            className="button"
            onClick={() => void client.invalidateQueries({ queryKey: ['api'] })}
          >
            <RefreshCw size={16} />
            새로고침
          </button>
        }
      />
      <NavTabs
        items={[
          { to: '/settings/models', label: '사내 모델' },
          { to: '/settings/routing', label: '질의·Agent별 모델 지정' },
          { to: '/settings/data', label: '데이터 연결' },
          { to: '/settings/backend', label: '백엔드 연결' },
        ]}
      />
      <Notice>
        사용자·Agent 인증은 제외되어 있습니다. 보고서 접수는 Job Controller, 정기 일정 관리는
        Backend가 처리합니다. 연결되지 않은 서비스는 미연결로 표시합니다.
      </Notice>
      <div className="backend-health-grid">
        <Panel>
          <div className="backend-health">
            <Server size={23} />
            <div>
              <h2>Go Backend</h2>
              <p>API v1 · 계약 1.3</p>
            </div>
            <Badge
              status={health.isSuccess ? 'healthy' : health.isPending ? 'queued' : 'unavailable'}
              label={health.isSuccess ? '연결됨' : health.isPending ? '확인 중' : '연결 불가'}
            />
          </div>
        </Panel>
        <Panel>
          <div className="backend-health">
            <Database size={23} />
            <div>
              <h2>PostgreSQL</h2>
              <p>저장소·스키마 준비 상태</p>
            </div>
            <Badge
              status={health.isSuccess ? 'healthy' : 'unknown'}
              label={health.isSuccess ? '준비 완료' : '확인 필요'}
            />
          </div>
        </Panel>
      </div>
      {health.isError && (
        <div className="form-error" role="alert">
          {message(health.error)}
        </div>
      )}
      <Panel
        title="소유 모듈 연결"
        description="각 모듈을 연결하면 해당 업무 API가 활성화됩니다. 연결되지 않은 기능은 503으로 응답합니다."
      >
        <div className="backend-modules">
          {modules.data?.items.map((m) => (
            <div className="backend-module" key={m.module}>
              {m.status === 'available' ? <CheckCircle2 size={18} /> : <Unplug size={18} />}
              <strong>{moduleLabels[m.module] || m.module}</strong>
              <Badge
                status={m.status === 'available' ? 'healthy' : 'unknown'}
                label={
                  m.status === 'available'
                    ? '연결됨'
                    : m.status === 'degraded'
                      ? '점검 필요'
                      : '미연결'
                }
              />
            </div>
          ))}
        </div>
        {modules.isError && <p className="backend-note">모듈 상태를 가져오지 못했습니다.</p>}
        {modules.isPending && <p className="backend-note">모듈 상태 확인 중…</p>}
      </Panel>
      <Notice>
        지식 초안 작성·검토·발행은{' '}
        <Link className="text-link" to="/knowledge">
          지식·Runbook
        </Link>
        에서 관리합니다.
      </Notice>
    </div>
  );
}
