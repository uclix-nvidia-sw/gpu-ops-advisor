import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Field, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, DataView, EvidenceDialog, More, QueryState } from '../components/live';
import {
  errorText,
  localInput,
  num,
  obj,
  queryPath,
  str,
  useCommand,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { formatDate } from '../lib/domain';
import { useApp } from '../lib/store';
import { IncidentDebug, RcaResult } from '../components/RcaDebug';
import { ReportContent } from '../components/ReportContent';
export function ResultPage({ kind }: { kind: string }) {
  const { id } = useParams(),
    app = useApp(),
    q = useResource(
      id
        ? `/${kind === 'analysis' ? 'analyses' : kind === 'report' ? 'reports' : 'incidents'}/${id}`
        : null,
      undefined,
      true,
    ),
    cmd = useCommand();
  const [evidence, setEvidence] = useState(''),
    [status, setStatus] = useState(''),
    [reason, setReason] = useState(''),
    [downloadError, setDownloadError] = useState(''),
    [downloading, setDownloading] = useState(false);
  const r = q.data || {};
  const download = async (format: string) => {
    setDownloading(true);
    setDownloadError('');
    try {
      const response = await fetch(`/api/v1/reports/${id}/export?format=${format}`);
      if (!response.ok) {
        const body = await response.json();
        throw new Error(str(obj(body.error).message, '내보내기에 실패했습니다.'));
      }
      const blob = await response.blob(),
        url = URL.createObjectURL(blob),
        a = document.createElement('a');
      a.href = url;
      a.download = `report-${id}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setDownloadError(errorText(e));
    } finally {
      setDownloading(false);
    }
  };
  return (
    <div className="page">
      <PageHead
        eyebrow={kind === 'incident' ? 'INCIDENT DETAIL' : 'SAVED RESULT'}
        title={
          kind === 'incident' ? '사건 상세' : kind === 'report' ? '운영 보고서' : 'RCA 조사 결과'
        }
        description={id || ''}
        actions={
          <>
            {kind === 'report' &&
              r.result_ref != null &&
              ['html', 'csv'].map((format) => (
                <button
                  className={`button ${format === 'html' ? 'primary' : ''}`}
                  key={format}
                  disabled={downloading}
                  onClick={() => download(format)}
                >
                  {format.toUpperCase()} 다운로드
                </button>
              ))}
            <Link className="button" to={kind === 'report' ? '/reports' : '/cases'}>
              목록으로
            </Link>
          </>
        }
      />
      <CommandError error={downloadError} />
      <QueryState query={q}>
        <Panel title={str(r.title, kind === 'incident' ? '사건 관측' : '저장된 결과')}>
          <div className="live-padding stack">
            <div className="head-actions">
              {kind !== 'incident' && <Badge status={str(r.status)} />}
              {kind !== 'incident' && <Badge status={str(r.result_status) || null} />}
              <span>{formatDate(str(r.created_at))}</span>
            </div>
            {kind === 'report' ? (
              <ReportContent value={r.result} request={r} onEvidence={setEvidence} />
            ) : kind === 'incident' ? (
              <IncidentDebug incident={r} />
            ) : (
              <RcaResult key={str(r.id)} job={r} onEvidence={setEvidence} />
            )}
            <div className="head-actions">
              {kind !== 'incident' && (
                <Link className="button" to={`/jobs/${id}`}>
                  작업 상태·시도 이력
                </Link>
              )}
              {kind === 'report' && (
                <Link className="button" to={`/reports/new?parent_job_id=${id}`}>
                  새 조건으로 보고서 요청
                </Link>
              )}
            </div>
            {kind === 'incident' && app.canOperate && (
              <form
                className="stack"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (
                    await cmd.run(
                      `/incidents/${id}`,
                      { review_status: status, memo: reason.trim() },
                      { method: 'PATCH', version: num(r.version) },
                    )
                  ) {
                    setReason('');
                    setStatus('');
                    app.notify('사건 상태 변경을 저장했습니다.');
                  }
                }}
              >
                <div className="form-grid">
                  <Field label="검토 상태">
                    <select required value={status} onChange={(e) => setStatus(e.target.value)}>
                      <option value="">선택</option>
                      {['unreviewed', 'reviewing', 'reviewed'].map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="메모">
                    <input required value={reason} onChange={(e) => setReason(e.target.value)} />
                  </Field>
                </div>
                <CommandError error={cmd.error} />
                <button className="button primary" disabled={cmd.busy || !status}>
                  상태 변경
                </button>
              </form>
            )}
          </div>
        </Panel>
        <Reviews
          id={id!}
          subject={kind === 'incident' ? 'incident' : 'job'}
          target={obj(r.target)}
        />
      </QueryState>
      {evidence && <EvidenceDialog id={evidence} onClose={() => setEvidence('')} />}
    </div>
  );
}
function Reviews({ id, subject, target }: { id: string; subject: string; target: Row }) {
  const app = useApp(),
    q = useList(queryPath('/reviews', { subject_type: subject, subject_id: id, limit: 30 })),
    cmd = useCommand();
  const [kind, setKind] = useState('comment'),
    [text, setText] = useState(''),
    [refs, setRefs] = useState(''),
    [occurred, setOccurred] = useState(localInput(new Date())),
    [performed, setPerformed] = useState(''),
    [summary, setSummary] = useState(''),
    [targetText, setTarget] = useState(JSON.stringify(target, null, 2)),
    [supersedes, setSupersedes] = useState('');
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const body = {
        subject_type: subject,
        subject_id: id,
        kind,
        text: text.trim(),
        evidence_refs: refs
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
        ...(supersedes ? { supersedes_id: supersedes } : {}),
        ...(kind === 'action'
          ? {
              target: JSON.parse(targetText),
              performed_by: performed.trim(),
              action_summary: summary.trim(),
              occurred_at: new Date(`${occurred}+09:00`).toISOString(),
            }
          : {}),
      };
      if (await cmd.run('/reviews', body)) {
        setText('');
        setSupersedes('');
        app.notify('검토 기록을 저장했습니다.');
      }
    } catch (e) {
      cmd.setError(errorText(e));
    }
  };
  return (
    <Panel
      title="검토·조치 기록"
      description="기록은 추가 방식으로 저장되며, 정정 시 원본과 연결됩니다."
    >
      <div className="live-padding stack">
        <QueryState
          query={q}
          empty={!q.items.length}
          emptyTitle="아직 작성된 검토·조치 기록이 없습니다."
          emptyDescription="분석 결과와 별도로 검토 의견이나 수행한 조치를 기록할 수 있습니다."
        >
          <div className="stack">
            {q.items.map((v) => (
              <article className="data-item" key={str(v.id)}>
                <div className="head-actions">
                  <Badge status={str(v.kind)} />
                  <small>
                    {str(v.author)} · {formatDate(str(v.created_at))}
                  </small>
                  <button
                    className="text-link"
                    onClick={() => {
                      setSupersedes(str(v.id));
                      setKind(str(v.kind));
                      setText(str(obj(v.body).text));
                      setRefs(
                        Array.isArray(obj(v.body).evidence_refs)
                          ? (obj(v.body).evidence_refs as string[]).join('\n')
                          : '',
                      );
                    }}
                  >
                    정정 기록 작성
                  </button>
                </div>
                <DataView value={v.body} />
              </article>
            ))}
          </div>
        </QueryState>
        <More query={q} />
        <form className="stack" onSubmit={save}>
          {supersedes && (
            <Notice>
              정정 대상: {supersedes}
              <button className="button" type="button" onClick={() => setSupersedes('')}>
                정정 취소
              </button>
            </Notice>
          )}
          <Field label="기록 종류">
            <select value={kind} disabled={!!supersedes} onChange={(e) => setKind(e.target.value)}>
              <option value="comment">의견</option>
              <option value="review">검토</option>
              {app.canOperate && <option value="action">수행한 조치</option>}
            </select>
          </Field>
          <Field label="기록 내용">
            <textarea required rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          {kind === 'action' && (
            <>
              <div className="form-grid">
                <Field label="실제 조치 시각 (KST)">
                  <input
                    required
                    type="datetime-local"
                    value={occurred}
                    onChange={(e) => setOccurred(e.target.value)}
                  />
                </Field>
                <Field label="수행자">
                  <input
                    required
                    value={performed}
                    onChange={(e) => setPerformed(e.target.value)}
                  />
                </Field>
              </div>
              <Field label="조치 요약">
                <input required value={summary} onChange={(e) => setSummary(e.target.value)} />
              </Field>
              <Field
                label="조치 대상 (JSON)"
                hint="kind, cluster_id 및 GPU UUID·Node UID·Pod UID와 Namespace를 입력합니다."
              >
                <textarea required value={targetText} onChange={(e) => setTarget(e.target.value)} />
              </Field>
            </>
          )}
          <Field label="근거 ID (한 줄에 하나)">
            <textarea rows={2} value={refs} onChange={(e) => setRefs(e.target.value)} />
          </Field>
          <CommandError error={cmd.error} />
          <button className="button primary" disabled={cmd.busy || !text.trim()}>
            기록 저장
          </button>
        </form>
      </div>
    </Panel>
  );
}
