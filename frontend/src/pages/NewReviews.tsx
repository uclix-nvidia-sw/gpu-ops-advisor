import { useNewDraft, clearNewDraft } from '../lib/newDraft';
import { Field, Notice, Panel } from '../components/ui';
import { CommandError, More, QueryState } from '../components/live';
import {
  localInput,
  obj,
  queryPath,
  str,
  strings,
  useCommand,
  useList,
  type Row,
} from '../lib/live';
import { useApp } from '../lib/store';
import { formatDate } from '../lib/domain';
import { assetTarget } from './Fleet';

export function NewReviews({
  id,
  subject,
  scope,
  readOnly = false,
  reviewStatus,
}: {
  id: string;
  subject: string;
  scope?: Row;
  readOnly?: boolean;
  reviewStatus?: string;
}) {
  const app = useApp(),
    cmd = useCommand();
  const q = useList(queryPath('/reviews', { subject_type: subject, subject_id: id, limit: 30 }));
  const key = `review/${subject}/${id}`;
  const [kind, setKind] = useNewDraft(`${key}/kind`, 'comment'),
    [text, setText] = useNewDraft(`${key}/text`, ''),
    [performed, setPerformed] = useNewDraft(`${key}/performed`, ''),
    [summary, setSummary] = useNewDraft(`${key}/summary`, ''),
    [occurred, setOccurred] = useNewDraft(`${key}/occurred`, localInput(new Date())),
    [correction, setCorrection] = useNewDraft<Row | null>(`${key}/correction`, null),
    [chosen, setChosen] = useNewDraft(`${key}/chosen`, ''),
    [assetKind, setAssetKind] = useNewDraft(`${key}/assetKind`, 'node');
  const clusters = Array.isArray(scope?.clusters) ? scope.clusters.map(obj) : [];
  const [selectedCluster, setCluster] = useNewDraft(`${key}/selectedCluster`, '');
  const cluster = clusters.find((c) => c.cluster_id === selectedCluster) || clusters[0];
  const at = Date.parse(`${occurred}+09:00`);
  const assets = useList(
    !readOnly && kind === 'action' && cluster && Number.isFinite(at)
      ? queryPath('/assets', {
          scope,
          cluster: cluster.cluster_id,
          kind: assetKind,
          at: new Date(at).toISOString(),
          limit: 50,
        })
      : null,
  );
  const available = assets.items.filter(
    (a) =>
      !Array.isArray(cluster?.namespaces) ||
      assetKind !== 'pod' ||
      (cluster.namespaces as string[]).includes(str(obj(a.attributes).namespace)),
  );
  const selected = available.find((a) => str(a.id) === chosen);
  const original = obj(correction?.body);
  const target = selected
    ? assetTarget(selected)
    : correction && kind === 'action' && Object.keys(obj(original.target)).length > 0
      ? obj(original.target)
      : null;
  const clear = () => {
    setText('');
    setCorrection(null);
    setPerformed('');
    setSummary('');
    setChosen('');
  };
  const missing = [
    !text.trim() && '내용',
    ...(kind === 'action'
      ? [
          !Number.isFinite(at) && '실제 수행 시각',
          !performed.trim() && '수행자',
          !summary.trim() && '조치 요약',
          !target && '조치 대상',
        ]
      : []),
  ].filter(Boolean);
  return (
    <section
      id={readOnly ? 'analysis-review-records' : 'new-review-records'}
      tabIndex={-1}
      aria-label={readOnly ? '분석별 이전 기록' : '검토·조치 기록'}
    >
      <Panel
        title={
          readOnly
            ? '이 분석에 남긴 이전 기록'
            : subject === 'incident'
              ? '사건 검토·조치 기록'
              : '보고서 검토·조치 기록'
        }
        description={
          readOnly
            ? '분석 작업에 저장된 이전 기록입니다. 사건 기록과 합치지 않고 원래 대상을 유지합니다.'
            : subject === 'incident'
              ? '사람이 남기는 기록입니다. 저장해도 검토 완료나 사건 종결로 바뀌지 않습니다. 실제 수행한 조치만 기록하세요.'
              : '보고서와 별도로 남기는 사람의 기록입니다. 실제 수행한 조치만 기록하세요.'
        }
      >
        <div className="live-padding stack">
          {!readOnly && subject === 'incident' && (
            <p className="muted">
              사건 검토 상태:{' '}
              {reviewStatus === 'reviewed'
                ? '검토 완료'
                : reviewStatus === 'reviewing'
                  ? '검토 중'
                  : reviewStatus === 'unreviewed'
                    ? '미검토'
                    : '미확인'}
              {' · '}
              <a href="#new-incident-state">검토·처리 상태 변경</a>
              {!!q.items.length && (
                <>
                  {' '}
                  · 최근 기록 {formatDate(str(q.items[0].created_at))} (
                  {str(q.items[0].author, '작성자 미확인')})
                </>
              )}
            </p>
          )}
          <QueryState
            query={q}
            empty={!q.items.length}
            emptyTitle="아직 남긴 기록이 없습니다."
            emptyDescription={
              readOnly
                ? '이 분석 작업에 저장된 이전 기록이 없습니다. 새 기록은 사건에 남기세요.'
                : '검토 의견이나 실제 수행한 조치를 아래에 기록할 수 있습니다.'
            }
          >
            {q.items.map((record) => {
              const body = obj(record.body);
              return (
                <article className="new-review" key={str(record.id)}>
                  <strong>
                    {record.kind === 'action'
                      ? '수행한 조치'
                      : record.kind === 'review'
                        ? '검토 기록'
                        : '검토 의견'}
                  </strong>
                  <small>
                    {formatDate(str(record.created_at))} · {str(record.author, '작성자 미확인')}
                  </small>
                  <p className="new-prose">{str(body.text)}</p>
                  {record.kind === 'action' && (
                    <p>
                      {formatDate(str(body.occurred_at))} · {str(body.performed_by)} ·{' '}
                      {str(body.action_summary)}
                    </p>
                  )}
                  {record.supersedes_id != null && <p>이전 기록을 정정한 내용입니다.</p>}
                  {!readOnly && (
                    <button
                      className="text-link"
                      onClick={() => {
                        setCorrection(record);
                        setKind(str(record.kind));
                        setText(str(body.text));
                        setPerformed(str(body.performed_by));
                        setSummary(str(body.action_summary));
                        setChosen('');
                        if (Number.isFinite(Date.parse(str(body.occurred_at))))
                          setOccurred(localInput(new Date(str(body.occurred_at))));
                      }}
                    >
                      정정 기록 작성
                    </button>
                  )}
                </article>
              );
            })}
          </QueryState>
          <More query={q} />
          {!readOnly && (
            <form
              className="stack"
              data-dirty={!!(text || performed || summary || correction)}
              onSubmit={async (e) => {
                e.preventDefault();
                if (kind === 'action' && (!target || !Number.isFinite(at))) return;
                const response = await cmd.run('/reviews', {
                  subject_type: subject,
                  subject_id: id,
                  kind,
                  text: text.trim(),
                  evidence_refs: correction ? strings(original.evidence_refs) : [],
                  ...(correction ? { supersedes_id: correction.id } : {}),
                  ...(kind === 'action'
                    ? {
                        target,
                        occurred_at: new Date(at).toISOString(),
                        performed_by: performed.trim(),
                        action_summary: summary.trim(),
                      }
                    : {}),
                });
                if (response) {
                  clear();
                  clearNewDraft(key);
                  app.notify(
                    subject === 'incident'
                      ? '사건 기록을 저장했습니다. 검토·처리 상태는 유지됩니다.'
                      : '보고서 기록을 저장했습니다.',
                  );
                }
              }}
            >
              {correction && (
                <Notice>
                  선택한 기록을 정정합니다. 원본과 연결된 근거는 유지됩니다.
                  <button type="button" className="text-link" onClick={clear}>
                    정정 취소
                  </button>
                </Notice>
              )}
              <Field label="기록 종류">
                <select
                  value={kind}
                  disabled={!!correction}
                  onChange={(e) => setKind(e.target.value)}
                >
                  <option value="comment">검토 의견</option>
                  <option value="review">검토 기록</option>
                  <option value="action">수행한 조치</option>
                </select>
              </Field>
              <Field label="내용">
                <textarea
                  required
                  rows={3}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </Field>
              {kind === 'action' && (
                <>
                  <Notice>
                    조치 대상은 이 {subject === 'incident' ? '사건' : '보고서'}에 저장된 범위에서
                    실제 수행 시각에 관측된 자산으로 제한합니다.
                    {!clusters.length &&
                      ' 저장된 범위를 확인할 수 없어 조치 기록을 저장할 수 없습니다. 검토 의견은 남길 수 있습니다.'}
                  </Notice>
                  <div className="new-form-grid">
                    <Field label="실제 수행 시각 · 한국 시간">
                      <input
                        required
                        type="datetime-local"
                        value={occurred}
                        onChange={(e) => {
                          setOccurred(e.target.value);
                          setChosen('');
                        }}
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
                  <Field label="수행한 조치 요약">
                    <input required value={summary} onChange={(e) => setSummary(e.target.value)} />
                  </Field>
                  <div className="new-form-grid">
                    <Field label="클러스터">
                      <select
                        value={str(cluster?.cluster_id)}
                        onChange={(e) => {
                          setCluster(e.target.value);
                          setChosen('');
                        }}
                      >
                        {clusters.map((c) => (
                          <option key={str(c.cluster_id)}>{str(c.cluster_id)}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="대상 종류">
                      <select
                        value={assetKind}
                        onChange={(e) => {
                          setAssetKind(e.target.value);
                          setChosen('');
                        }}
                      >
                        <option value="node">Node</option>
                        <option value="gpu">GPU</option>
                        <option value="pod">Pod</option>
                      </select>
                    </Field>
                  </div>
                  {correction &&
                    Object.keys(original.target ? obj(original.target) : {}).length > 0 && (
                      <Notice>대상을 새로 선택하지 않으면 원본의 조치 대상을 유지합니다.</Notice>
                    )}
                  <QueryState
                    query={assets}
                    empty={!available.length}
                    emptyTitle="수행 시각에 확인된 대상이 없습니다."
                    emptyDescription="대상을 확인할 수 없으면 조치 기록을 저장할 수 없습니다. 검토 의견은 남길 수 있습니다."
                  >
                    <Field label="조치 대상">
                      <select value={chosen} onChange={(e) => setChosen(e.target.value)}>
                        <option value="">대상을 선택하세요</option>
                        {available.map((a, i) => {
                          const attrs = obj(a.attributes);
                          return (
                            <option key={str(a.id)} value={str(a.id)}>
                              {str(attrs.node) ||
                                str(attrs.pod_name) ||
                                str(attrs.name) ||
                                '이름 미확인'}{' '}
                              · {str(attrs.model) || assetKind} ·{' '}
                              {assetKind === 'gpu'
                                ? `장치 ${str(a.subject_key).slice(-8)}`
                                : `목록 ${i + 1}`}
                            </option>
                          );
                        })}
                      </select>
                    </Field>
                  </QueryState>
                  <More query={assets} />
                  <Notice>
                    수행자 이름은 입력 기록입니다. 인증된 신원이나 조치 효과를 자동으로 검증하지
                    않습니다.
                  </Notice>
                </>
              )}
              <CommandError error={cmd.error} />
              <p id="new-review-save-help" className="muted" aria-live="polite">
                {!app.canOperate
                  ? '연결과 운영 가능 상태를 확인한 뒤 기록할 수 있습니다.'
                  : missing.length
                    ? `저장하려면 입력하세요: ${missing.join(', ')}`
                    : '입력이 준비되었습니다. 기록 저장을 누르세요.'}
              </p>
              <button
                aria-describedby="new-review-save-help"
                className="button primary"
                disabled={
                  cmd.busy ||
                  !app.canOperate ||
                  !text.trim() ||
                  (kind === 'action' &&
                    (!target || !performed.trim() || !summary.trim() || !Number.isFinite(at)))
                }
              >
                기록 저장
              </button>
            </form>
          )}
        </div>
      </Panel>
    </section>
  );
}
