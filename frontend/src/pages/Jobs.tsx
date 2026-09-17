import { ArrowLeft, ArrowUpRight, CheckCircle2, RotateCcw, XCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Empty, Field, Modal, Notice, PageHead, Panel, SearchBox } from '../components/ui';
import { formatDate, inScope, scopeLabel } from '../lib/domain';
import { advanceJobs } from '../lib/jobs';
import { useApp, useDatabase } from '../lib/store';
export function DemoJobRunner() {
  const { db, mutate } = useDatabase();
  const active = db?.jobs.some((j) => ['queued', 'running', 'retry_wait'].includes(j.status));
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void mutate((d) => advanceJobs(d));
    }, 1200);
    return () => clearInterval(timer);
  }, [active]);
  return null;
}
export function Jobs() {
  const { db } = useDatabase();
  const app = useApp();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [kind, setKind] = useState('all');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const rows =
    db?.jobs
      .filter(
        (j) =>
          j.scope.clusters.some((c) => inScope(app.scope, c.cluster_id)) &&
          j.title.includes(search) &&
          (status === 'all' || j.status === status) &&
          (kind === 'all' || j.kind === kind) &&
          (!from || j.created_at >= `${from}T00:00:00+09:00`) &&
          (!to || Date.parse(j.created_at) < Date.parse(`${to}T00:00:00+09:00`) + 86400000),
      )
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)) || [];
  return (
    <div className="page">
      <PageHead
        eyebrow="JOB HISTORY"
        title="작업 이력"
        description="조사와 보고서의 접수부터 결과 저장까지, 작업의 진행과 시도를 확인합니다."
      />
      <div className="toolbar">
        <SearchBox value={search} onChange={setSearch} placeholder="작업 제목 검색" />
        <select aria-label="작업 종류" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="all">모든 작업</option>
          <option value="rca">RCA 조사</option>
          <option value="report">보고서</option>
        </select>
        <select
          aria-label="실행 상태 필터"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="all">모든 상태</option>
          {['queued', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled', 'expired'].map(
            (s) => (
              <option key={s}>{s}</option>
            ),
          )}
        </select>
        <input
          aria-label="작업 생성 시작일"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <input
          aria-label="작업 생성 종료일"
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
      <Panel>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>작업 / ID</th>
                <th>종류</th>
                <th>접수 시각</th>
                <th>진행 단계</th>
                <th>실행 상태</th>
                <th>산출 상태</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link to={`/jobs/${j.id}`}>
                      <b>{j.title}</b>
                      <small className="mono">
                        {j.id.slice(0, 8)} · 시도 {j.attempt_no}
                      </small>
                    </Link>
                  </td>
                  <td>{j.kind === 'rca' ? 'RCA 조사' : '보고서'}</td>
                  <td>{formatDate(j.created_at)}</td>
                  <td>{j.stage}</td>
                  <td>
                    <Badge status={j.status} />
                  </td>
                  <td>
                    <Badge status={j.result_status} />
                  </td>
                  <td>
                    <Link className="text-link" to={`/jobs/${j.id}`}>
                      상세
                      <ArrowUpRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty />}
        </div>
        <div className="table-footer">
          접수 시각 내림차순<span>{rows.length}개 작업</span>
        </div>
      </Panel>
    </div>
  );
}
export function JobDetail() {
  const { id } = useParams();
  const { db, mutate } = useDatabase();
  const app = useApp();
  const job = db?.jobs.find((j) => j.id === id);
  const [action, setAction] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const version = useRef(0);
  const [busy, setBusy] = useState(false);
  if (!db)
    return (
      <div className="loading" role="status">
        작업 조회 중…
      </div>
    );
  if (!job) return <Empty title="없거나 접근할 수 없는 항목" />;
  const resultLink =
    job.kind === 'report'
      ? `/reports/${job.id}`
      : job.incident_id
        ? `/incidents/${job.incident_id}`
        : `/analyses/${job.id}`;
  const perform = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await mutate((d) => {
        const j = d.jobs.find((j) => j.id === id)!;
        if (j.version !== version.current) {
          version.current = j.version;
          throw new Error('작업 상태가 변경되었습니다. 최신 상태를 확인한 후 다시 요청해 주세요.');
        }
        if (action === 'cancel') {
          if (!j.can_cancel) throw new Error('이미 완료되었거나 취소할 수 없는 작업입니다.');
          j.cancel_requested_at = new Date().toISOString();
          j.termination_reason = reason;
        } else {
          if (!j.can_retry) throw new Error('현재 작업은 재시도할 수 없습니다.');
          j.status = 'retry_wait';
          j.started_at = new Date().toISOString();
          j.attempt_no++;
          j.stage = '재시도 대기';
          j.can_retry = false;
          j.can_cancel = true;
        }
        j.version++;
      });
      app.notify(
        action === 'cancel'
          ? '취소 요청이 접수되었습니다. 최종 상태를 확인합니다.'
          : '동일 작업의 재시도가 접수되었습니다.',
      );
      setAction('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page">
      <Link className="back-link" to="/jobs">
        <ArrowLeft size={15} />
        작업 이력
      </Link>
      <PageHead
        eyebrow="JOB DETAIL"
        title={job.title}
        description={`작업 ID ${job.id}`}
        actions={
          <>
            <Badge status={job.status} />
            {job.status === 'succeeded' && (
              <Link className="button primary" to={resultLink}>
                저장 결과 보기
                <ArrowUpRight size={16} />
              </Link>
            )}
          </>
        }
      />
      <div className="two-column detail-columns">
        <div className="stack">
          <Panel
            title="실행 진행"
            description="데모 작업의 수명주기입니다. 실제 Worker는 연결되지 않았습니다."
          >
            <div className="job-steps">
              {['접수', '관측 조회', '입력 확인', '결과 저장'].map((s, i) => (
                <div
                  key={s}
                  className={
                    job.status === 'succeeded' || i === 0 || (job.status === 'running' && i < 3)
                      ? 'done'
                      : ''
                  }
                >
                  <CheckCircle2 size={23} />
                  <span>{s}</span>
                </div>
              ))}
            </div>
            <div className="panel-body">
              <h3>{job.stage}</h3>
              {job.cancel_requested_at && job.status !== 'cancelled' && (
                <Notice tone="warning">취소 요청 접수 · 서버에 해당하는 데모 상태 확정 대기</Notice>
              )}
              {job.termination_reason && <Notice tone="warning">{job.termination_reason}</Notice>}
              <div className="inline-states">
                <span>
                  실행 <Badge status={job.status} />
                </span>
                <span>
                  산출 <Badge status={job.result_status} />
                </span>
              </div>
              {job.status === 'succeeded' && (
                <Notice>
                  실행 완료와 산출 가능은 별개의 상태입니다. 근거가 부족한 값은 결과에서 사유를
                  확인하세요.
                </Notice>
              )}
            </div>
          </Panel>
          <Panel title="시도 이력">
            <div className="panel-body">
              <dl className="details">
                <dt>누적 시도</dt>
                <dd>{job.attempt_no}회</dd>
                <dt>최근 단계</dt>
                <dd>{job.stage}</dd>
                <dt>종료 이유</dt>
                <dd>{job.termination_reason || '—'}</dd>
                <dt>전체 기한</dt>
                <dd>{formatDate(job.deadline_at)} KST</dd>
              </dl>
              <p className="muted">
                재시도는 같은 작업의 시도 횟수를 늘립니다. 전체 기한을 초기화하지 않습니다.
              </p>
            </div>
          </Panel>
        </div>
        <Panel title="접수 조건">
          <div className="panel-body stack">
            <dl className="details">
              <dt>종류</dt>
              <dd>{job.kind === 'rca' ? 'RCA 조사' : '운영 보고서'}</dd>
              <dt>저장 범위</dt>
              <dd>{scopeLabel(job.scope)}</dd>
              <dt>대상</dt>
              <dd>{job.target || '선택 범위 전체'}</dd>
              <dt>분석 기간</dt>
              <dd>
                {formatDate(job.time_range.start)} ~ {formatDate(job.time_range.end)} KST
              </dd>
              <dt>접수 시각</dt>
              <dd>{formatDate(job.created_at)}</dd>
              <dt>버전</dt>
              <dd>v{job.version}</dd>
              {job.parent_job_id && (
                <>
                  <dt>이전 작업</dt>
                  <dd>
                    <Link className="text-link" to={`/jobs/${job.parent_job_id}`}>
                      {job.parent_job_id.slice(0, 8)}
                    </Link>
                  </dd>
                </>
              )}
            </dl>
            {app.role === 'operator' && (
              <>
                {job.can_cancel && !job.cancel_requested_at && (
                  <button
                    className="button danger"
                    onClick={() => {
                      version.current = job.version;
                      setReason('');
                      setAction('cancel');
                    }}
                  >
                    <XCircle size={16} />
                    작업 취소 요청
                  </button>
                )}
                {job.can_retry && (
                  <button
                    className="button"
                    onClick={() => {
                      version.current = job.version;
                      setReason('');
                      setAction('retry');
                    }}
                  >
                    <RotateCcw size={16} />
                    동일 작업 재시도
                  </button>
                )}
                <Link
                  className="button"
                  to={
                    job.kind === 'report'
                      ? `/reports/new?parent=${job.id}`
                      : `/analyses/new?parent=${job.id}`
                  }
                >
                  새 {job.kind === 'report' ? '보고서' : '분석'} 요청
                  <ArrowUpRight size={15} />
                </Link>
              </>
            )}
            <small className="muted">화면을 닫아도 접수된 작업은 취소되지 않습니다.</small>
          </div>
        </Panel>
      </div>
      {action && (
        <Modal
          title={action === 'cancel' ? '작업 취소 요청' : '동일 작업 재시도'}
          onClose={() => setAction('')}
        >
          <form className="stack" onSubmit={perform}>
            <Notice>
              {action === 'cancel'
                ? '취소 요청 이후 최종 실행 상태를 확인합니다.'
                : '기존 작업 ID·전체 기한을 유지하고 새 시도를 진행합니다.'}
            </Notice>
            <Field label="요청 사유 *">
              <textarea
                autoFocus
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
              />
            </Field>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary" disabled={busy || !reason.trim()}>
              {busy ? '요청 중…' : '요청 제출'}
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
