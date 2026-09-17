import {
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  ClipboardList,
  Download,
  FileText,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Empty, Evidence, Field, Modal, Notice, PageHead, Panel } from '../components/ui';
import { analysisId, reportId, topics } from '../data/fixtures';
import {
  csvCell,
  escapeHtml,
  formatDate,
  incidentTransitions,
  labels,
  scopeLabel,
} from '../lib/domain';
import { useApp, useDatabase } from '../lib/store';
export function ResultPage({ kind }: { kind: 'incident' | 'analysis' | 'report' }) {
  const { id } = useParams();
  const app = useApp();
  const { db, mutate } = useDatabase();
  const incident = kind === 'incident' ? db?.incidents.find((i) => i.id === id) : undefined;
  const job = db?.jobs.find(
    (j) =>
      j.id === (incident ? incident.analysis_id : id) &&
      j.kind === (kind === 'report' ? 'report' : 'rca'),
  );
  const [evidence, setEvidence] = useState(false);
  const [modal, setModal] = useState('');
  const [reason, setReason] = useState('');
  const [nextStatus, setNextStatus] = useState('');
  const [author, setAuthor] = useState('김운영');
  const [target, setTarget] = useState('');
  const [performed, setPerformed] = useState('2026-09-16T14:15');
  const [recordType, setRecordType] = useState('review');
  const [supersedes, setSupersedes] = useState<string | undefined>();
  const [error, setError] = useState('');
  const [savedVersion, setSavedVersion] = useState(0);
  if (!db)
    return (
      <div className="loading" role="status">
        결과 조회 중…
      </div>
    );
  if ((kind === 'incident' && !incident) || (kind !== 'incident' && !job))
    return <Empty title="없거나 접근할 수 없는 항목" />;
  const seeded = job?.id === analysisId || job?.id === reportId;
  const title = incident ? incident.title : job!.title;
  const report = kind === 'report';
  const records = db.reviews.filter((r) => r.subject_id === (incident?.id || job?.id));
  const exportReport = (format: 'html' | 'csv') => {
    if (!job) return;
    const rows = (job.topic_ids || []).map((t) => [
      t,
      topics[Number(t.slice(1)) - 1],
      seeded && ['O01', 'O11'].includes(t) ? 'ready' : 'blocked',
      seeded && t === 'O01' ? 64 : seeded && t === 'O11' ? '7 / 8 Nodes 수신' : null,
    ]);
    const text =
      format === 'csv'
        ? '\uFEFF' +
          [['주제 ID', '주제', '산출 상태', '값'], ...rows]
            .map((row) => row.map((v) => csvCell(v)).join(','))
            .join('\r\n')
        : `<!doctype html><html lang="ko"><meta charset="utf-8"><title>${escapeHtml(job.title)}</title><style>body{font-family:sans-serif;max-width:900px;margin:60px auto;color:#233e33}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:16px;text-align:left}</style><h1>${escapeHtml(job.title)}</h1><p>데모 저장 보고서 · 실제 운영 집계 아님</p><p>${escapeHtml(scopeLabel(job.scope))}</p><p>${escapeHtml(job.time_range.start)} ~ ${escapeHtml(job.time_range.end)}</p><table><tr><th>주제</th><th>산출</th><th>값</th></tr>${rows.map((r) => `<tr><td>${escapeHtml(String(r[1]))}</td><td>${escapeHtml(labels[String(r[2])])}</td><td>${r[3] ?? '근거 부족'}</td></tr>`).join('')}</table></html>`;
    const blob = new Blob([text], {
      type: format === 'csv' ? 'text/csv;charset=utf-8' : 'text/html;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dsx-demo-report-${job.id}.${format}`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    app.notify('저장된 데모 보고서의 다운로드를 요청했습니다.');
  };
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (!reason.trim()) throw new Error('사유 또는 기록 내용을 입력해 주세요.');
      await mutate((d) => {
        if (modal === 'status') {
          const i = d.incidents.find((i) => i.id === incident!.id)!;
          if (i.version !== savedVersion)
            throw new Error('사건 버전이 변경되었습니다. 창을 닫고 최신 상태를 확인해 주세요.');
          if (!incidentTransitions[i.status]?.includes(nextStatus))
            throw new Error('허용되지 않는 상태 변경입니다.');
          i.status = nextStatus;
          i.version++;
          i.history.push({ at: new Date().toISOString(), status: nextStatus, reason, author });
        } else {
          d.reviews.push({
            id: crypto.randomUUID(),
            subject_id: incident?.id || job!.id,
            type: recordType,
            content: reason,
            author,
            target: target || job?.target || incident?.node || '선택 범위',
            performed_at: `${performed}:00+09:00`,
            supersedes_id: supersedes,
          });
        }
      });
      setModal('');
      app.notify('데모 기록이 저장되었습니다.');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="page">
      <Link className="back-link" to={report ? '/reports' : '/cases'}>
        <ArrowLeft size={15} />
        {report ? '운영 보고서' : '조사 목록'}
      </Link>
      <PageHead
        eyebrow={report ? 'SAVED REPORT' : 'INVESTIGATION RESULT'}
        title={title}
        description={
          incident
            ? `${incident.label} · ${incident.node} · ${incident.cluster_id.toUpperCase()}`
            : `저장 결과 · ${id}`
        }
        actions={
          <>
            {job && (
              <Link className="button" to={`/jobs/${job.id}`}>
                작업 상세
                <ArrowUpRight size={15} />
              </Link>
            )}
            <button
              className="button"
              onClick={() => app.ask(`${title} · 저장 결과 ${job?.id || incident?.id}`)}
            >
              <Sparkles size={15} />
              추가 질문
            </button>
          </>
        }
      />
      <div className="result-summary">
        <div>
          <small>대상 / 고정 범위</small>
          <b>{job ? scopeLabel(job.scope) : `${incident!.cluster_id} / ${incident!.node}`}</b>
        </div>
        <div>
          <small>분석 기간 (KST)</small>
          <b>
            {job
              ? `${formatDate(job.time_range.start)} ~ ${formatDate(job.time_range.end)}`
              : '조사 미접수'}
          </b>
        </div>
        <div>
          <small>실행 상태</small>
          {job ? <Badge status={job.status} /> : <span>—</span>}
        </div>
        <div>
          <small>산출 상태</small>
          <Badge status={job?.result_status || null} />
        </div>
      </div>
      {incident && (
        <Panel>
          <div className="incident-control">
            <div>
              <span className="muted">사건 운영 상태</span>
              <Badge status={incident.status} />
              <small>v{incident.version} · 분석 완료와 별개</small>
            </div>
            {app.role === 'operator' && (
              <button
                className="button"
                onClick={() => {
                  setNextStatus(incidentTransitions[incident.status]?.[0] || '');
                  setReason('');
                  setSavedVersion(incident.version);
                  setError('');
                  setModal('status');
                }}
              >
                사건 상태 변경
              </button>
            )}
          </div>
        </Panel>
      )}
      {!job ? (
        <Panel>
          <Empty
            title="아직 접수된 조사가 없습니다."
            description="사건의 대상과 맥락을 유지해 새 조사를 요청할 수 있습니다."
            action={
              <Link className="button primary" to={`/analyses/new?incident=${incident!.id}`}>
                조사 시작
              </Link>
            }
          />
        </Panel>
      ) : job.status !== 'succeeded' ? (
        <Panel>
          <Empty
            title="저장된 결과가 아직 없습니다."
            description="작업 상세에서 실행 상태와 종료 사유를 확인해 주세요."
            action={
              <Link className="button primary" to={`/jobs/${job.id}`}>
                작업 진행 확인
              </Link>
            }
          />
        </Panel>
      ) : (
        <>
          {job.narrative_status === 'omitted' && (
            <Notice>
              AI 설명 생성 생략 · 데모에는 요청한 기간의 실제 관측 근거가 없습니다. 실행 완료와 분석
              가능을 구분해 표시합니다.
            </Notice>
          )}
          {report ? (
            <>
              <Panel
                title="주제별 분석 결과"
                description="독립적으로 산출 가능한 항목은 유지하고, 부족한 값은 0으로 표시하지 않습니다."
              >
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>주제</th>
                        <th>산출 상태</th>
                        <th>값 / 단위</th>
                        <th>산출 범위·부족 사유</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.topic_ids?.map((t) => {
                        const ready = seeded && ['O01', 'O11'].includes(t);
                        return (
                          <tr key={t}>
                            <td>
                              <span className="code-label">{t}</span>
                              <b>{topics[Number(t.slice(1)) - 1]}</b>
                            </td>
                            <td>
                              <Badge status={ready ? 'ready' : 'blocked'} />
                            </td>
                            <td>
                              {ready
                                ? t === 'O01'
                                  ? '64 GPUs / 8 Nodes'
                                  : '7 / 8 Nodes 수신'
                                : '근거 부족'}
                            </td>
                            <td>
                              {ready
                                ? '기준 시각의 예시 스냅샷'
                                : t === 'O09'
                                  ? '기간 내 실제 전력·에너지 이력 없음'
                                  : t === 'O10'
                                    ? '조치 기록·전후 비교 입력 검증 필요'
                                    : '선택 기간의 공동 관측·할당 이력 필요'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>
              <div className="two-column">
                <Panel title="보고서 해석">
                  <div className="panel-body">
                    <h3>현재 명세와 기간 집계는 다릅니다.</h3>
                    <p className="muted">
                      GPU 대수가 확인되더라도 과거 할당 이력이 없으면 GPU-hours를 계산할 수
                      없습니다. 저활동 후보는 자원 낭비나 회수 가능을 확정하지 않습니다.
                    </p>
                  </div>
                </Panel>
                <Panel title="저장본 내보내기">
                  <div className="panel-body stack">
                    <p className="muted">동일 저장 결과를 HTML 또는 집계 CSV로 내려받습니다.</p>
                    <div className="form-actions">
                      <button className="button" onClick={() => exportReport('html')}>
                        <FileText size={15} />
                        HTML 보고서
                      </button>
                      <button className="button" onClick={() => exportReport('csv')}>
                        <Download size={15} />
                        집계 CSV
                      </button>
                    </div>
                  </div>
                </Panel>
              </div>
            </>
          ) : (
            <div className="two-column detail-columns">
              <div className="stack">
                <Panel title="확인된 사실" description="관측 사실과 추론을 분리합니다.">
                  <div className="panel-body">
                    <div className="finding">
                      <CheckCircle2 size={19} />
                      <div>
                        <h3>
                          {seeded ? '13:42:18 · Xid 79 오류 관측' : '조사 대상과 요청 맥락 접수'}
                        </h3>
                        <p>
                          {seeded
                            ? 'dgx-03 / GPU-c38a에서 GPU 응답 중단 메시지가 확인되었습니다.'
                            : `${job.target} · ${job.purpose_ids?.join(', ')} · 관측 근거 추가 필요`}
                        </p>
                      </div>
                    </div>
                    <div className="finding">
                      <CheckCircle2 size={19} />
                      <div>
                        <h3>
                          {seeded ? 'Pod 배치 확인 / GPU 관계 미확인' : '관계·영향·원인 판단 보류'}
                        </h3>
                        <p>
                          현재 배치를 과거 관계로 대체하지 않으며, 작업 영향은 별도 근거가
                          필요합니다.
                        </p>
                      </div>
                    </div>
                    <div className="fact-axes">
                      <div>
                        <small>관계 판단</small>
                        <Badge status={seeded ? 'partial' : 'blocked'} />
                      </div>
                      <div>
                        <small>작업 영향</small>
                        <Badge status="blocked" />
                      </div>
                      <div>
                        <small>원인 확정</small>
                        <Badge status="blocked" />
                      </div>
                    </div>
                  </div>
                </Panel>
                <Panel title="원인 후보와 근거">
                  <div className="panel-body stack">
                    <h3>
                      {seeded
                        ? 'PCIe 연결 또는 전원 경로 이상 가능성'
                        : '판단에 필요한 입력이 부족합니다.'}
                    </h3>
                    <Notice tone="warning">
                      원인 미확정 · 추가 확인이 필요합니다. 임의 신뢰도 수치는 제공하지 않습니다.
                    </Notice>
                    <dl className="details">
                      <dt>지지 근거</dt>
                      <dd>{seeded ? 'Xid 79 응답 중단 메시지' : '확보되지 않음'}</dd>
                      <dt>반박 근거</dt>
                      <dd>미확인 · 부재를 반박으로 해석하지 않음</dd>
                      <dt>부족 입력</dt>
                      <dd>
                        {seeded
                          ? '동시점 PCIe 로그, 전원 상태, 과거 GPU ↔ Pod UID 관계'
                          : '선택 대상·기간의 원본 관측, Pod UID·GPU 관계와 활동 입력'}
                      </dd>
                    </dl>
                    {seeded && (
                      <button className="button" onClick={() => setEvidence(true)}>
                        관측 근거 열기
                        <ArrowUpRight size={15} />
                      </button>
                    )}
                  </div>
                </Panel>
              </div>
              <Panel title="다음 확인 사항">
                <div className="panel-body stack">
                  <ol className="next-steps">
                    <li>사건 시각의 원본 로그와 GPU UUID를 대조합니다.</li>
                    <li>동일 시각 Pod UID 및 작업 중단 근거를 확인합니다.</li>
                    <li>운영자가 장비 경로를 확인하고 수행 기록을 남깁니다.</li>
                    <li>장비 회복과 업무 복구를 각각 재확인합니다.</li>
                  </ol>
                  <Link
                    className="runbook-link"
                    to={
                      seeded
                        ? '/knowledge?item=kb-xid79&revision=3'
                        : '/knowledge?item=kb-mapping&revision=1'
                    }
                  >
                    <span className="code-label">{seeded ? 'RUNBOOK · v3' : '참고 지식 · v1'}</span>
                    <b>{seeded ? 'Xid 79 점검 가이드' : 'Pod 배치와 GPU 관계 읽기'}</b>
                    <small>
                      {seeded
                        ? 'H100 / A100 · Driver 550.x'
                        : '관계·활동의 의미 · 호환 Runbook 미확정'}
                    </small>
                    <ArrowUpRight size={17} />
                  </Link>
                  <Notice>
                    자동 GPU reset·drain·reboot를 실행하지 않습니다. 실제 조치는 운영자가
                    판단합니다.
                  </Notice>
                </div>
              </Panel>
            </div>
          )}
          <Panel title="산출 기준·품질·버전">
            <div className="panel-body">
              <details>
                <summary>고정된 분석 기준 상세 보기</summary>
                <dl className="details advanced-fields">
                  <dt>기준 시각</dt>
                  <dd>{formatDate(job.time_range.end)} KST</dd>
                  <dt>관측률</dt>
                  <dd>{seeded ? '단기 스냅샷만 확인 · 공동 관측률 미확정' : '관측 입력 없음'}</dd>
                  <dt>제외 범위</dt>
                  <dd>과거 매핑 미보존 구간·수신 누락 구간</dd>
                  <dt>정책</dt>
                  <dd>DSX v1.1 · demo-policy-1</dd>
                  <dt>모델</dt>
                  <dd>미호출 · 고정 데모 결과</dd>
                  <dt>설명 상태</dt>
                  <dd>{job.narrative_status}</dd>
                  <dt>지식 revision</dt>
                  <dd>
                    {seeded ? 'KB-079 v3 · 이전 인용 유지' : '분석 인용 없음 · 별도 참고 지식 제공'}
                  </dd>
                </dl>
              </details>
            </div>
          </Panel>
        </>
      )}
      <Panel
        title="검토·실제 조치 기록"
        description="권고와 운영자가 실제 수행한 조치를 구분합니다."
        action={
          app.role === 'operator' ? (
            <button
              className="button"
              onClick={() => {
                setModal('review');
                setReason('');
                setTarget(job?.target || incident?.node || '');
                setSupersedes(undefined);
                setError('');
              }}
            >
              <ClipboardList size={15} />
              기록 추가
            </button>
          ) : null
        }
      >
        <div className="panel-body">
          {!records.length ? (
            <Empty
              title="아직 남겨진 기록이 없습니다."
              description="검토 의견이나 실제 조치를 기록하면 이곳에 이력으로 보존됩니다."
            />
          ) : (
            records.map((r) => (
              <div className="review-record" key={r.id}>
                <div>
                  <Badge status="neutral" label={r.type === 'action' ? '실제 조치' : '검토 의견'} />
                  <small>
                    {r.author} · {formatDate(r.performed_at)} · {r.target}
                  </small>
                </div>
                <p>{r.content}</p>
                {r.supersedes_id && (
                  <small>이전 기록 {r.supersedes_id.slice(0, 8)}의 정정본 · 원본 보존</small>
                )}
                {app.role === 'operator' && (
                  <button
                    className="text-button"
                    onClick={() => {
                      setModal('review');
                      setReason(r.content);
                      setTarget(r.target);
                      setRecordType(r.type);
                      setSupersedes(r.id);
                      setError('');
                    }}
                  >
                    정정 기록 추가
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </Panel>
      {incident && (
        <Panel title="사건 상태 변경 이력">
          <div className="panel-body">
            {incident.history.length ? (
              incident.history.map((h, i) => (
                <div className="history-row" key={i}>
                  <Badge status={h.status} />
                  <span>{h.reason}</span>
                  <small>
                    {h.author} · {formatDate(h.at)}
                  </small>
                </div>
              ))
            ) : (
              <p className="muted">상태 변경 이력이 없습니다.</p>
            )}
          </div>
        </Panel>
      )}
      {job && app.role === 'operator' && (
        <div className="form-actions">
          <Link
            className="button"
            to={
              report
                ? `/reports/new?parent=${job.id}`
                : `/analyses/new?parent=${job.id}${incident ? `&incident=${incident.id}` : ''}`
            }
          >
            <RefreshCw size={15} />
            {report ? '새 보고서 재생성' : '새 작업으로 재분석'}
          </Link>
          {incident && (
            <Link
              className="button primary"
              to={`/analyses/new?incident=${incident.id}&parent=${job.id}&recheck=1`}
            >
              현재 상태 재확인
              <ArrowUpRight size={15} />
            </Link>
          )}
        </div>
      )}
      {evidence && <Evidence onClose={() => setEvidence(false)} />}
      {modal && (
        <Modal
          title={modal === 'status' ? '사건 상태 변경' : '검토·실제 조치 기록'}
          onClose={() => setModal('')}
        >
          <form onSubmit={save} className="stack">
            {modal === 'status' ? (
              <Field label="변경할 상태">
                <select value={nextStatus} onChange={(e) => setNextStatus(e.target.value)}>
                  {incidentTransitions[incident!.status]?.map((s) => (
                    <option key={s} value={s}>
                      {labels[s]}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <>
                <Field label="기록 종류">
                  <select value={recordType} onChange={(e) => setRecordType(e.target.value)}>
                    <option value="review">검토 의견</option>
                    <option value="action">실제 수행한 조치</option>
                  </select>
                </Field>
                <div className="form-grid">
                  <Field label="대상 *">
                    <input required value={target} onChange={(e) => setTarget(e.target.value)} />
                  </Field>
                  <Field label="수행 시각 (KST) *">
                    <input
                      required
                      type="datetime-local"
                      value={performed}
                      onChange={(e) => setPerformed(e.target.value)}
                    />
                  </Field>
                </div>
              </>
            )}
            <Field label="담당 / 수행자 *">
              <input required value={author} onChange={(e) => setAuthor(e.target.value)} />
            </Field>
            <Field label={modal === 'status' ? '변경·종결 사유 *' : '기록 내용 *'}>
              <textarea
                required
                rows={4}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary" disabled={!reason.trim()}>
              기록 저장
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
