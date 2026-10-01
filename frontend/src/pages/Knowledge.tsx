import { useState, type FormEvent } from 'react';
import { Badge, Field, Modal, PageHead, Panel, SearchBox, Notice } from '../components/ui';
import { CommandError, DataView, More, QueryState } from '../components/live';
import {
  num,
  obj,
  queryPath,
  str,
  strings,
  useCommand,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { useApp } from '../lib/store';
import { RunbookContent } from '../components/RunbookContent';
export function Knowledge() {
  const app = useApp();
  const [state, setState] = useState('draft'),
    [kind, setKind] = useState(''),
    [search, setSearch] = useState(''),
    [filter, setFilter] = useState(''),
    [open, setOpen] = useState<Row | null>(null);
  const q = useList(
    app.ready
      ? queryPath('/knowledge', { scope: app.scope, state, kind, symptom: filter, limit: 30 })
      : null,
  );
  return (
    <div className="page">
      <PageHead
        eyebrow="KNOWLEDGE LIBRARY"
        title="지식·Runbook"
        description="운영 지식을 작성하고 검토·발행 이력을 관리합니다."
        actions={
          app.canKnowledge && (
            <button className="button primary" onClick={() => setOpen({})}>
              새 지식 작성
            </button>
          )
        }
      />
      <Panel title="지식 목록">
        <form
          className="live-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            setFilter(search.trim());
          }}
        >
          <Field label="발행 상태">
            <select value={state} onChange={(e) => setState(e.target.value)}>
              {[
                ['draft', '초안'],
                ['in_review', '검토 중'],
                ['reviewed', '검토 완료'],
                ['published', '발행됨'],
                ['retired', '폐기됨'],
              ].map(([v, l]) => (
                <option value={v} key={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
          <Field label="종류">
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">전체 종류</option>
              {['runbook', 'policy', 'data_dictionary', 'reference', 'case'].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          <SearchBox value={search} onChange={setSearch} placeholder="지식 내용 검색" />
          <button className="button">검색</button>
        </form>
        <QueryState query={q} empty={!q.items.length}>
          <div className="knowledge-live-grid">
            {q.items.map((k) => (
              <button className="knowledge-live-card" key={str(k.id)} onClick={() => setOpen(k)}>
                <div>
                  <Badge status={str(k.state)} />
                  <small>
                    {str(k.kind)} · revision {num(k.revision)}
                  </small>
                </div>
                <h3>{str(obj(k.content).title, '제목 없음')}</h3>
                <p>{str(obj(k.content).description, str(obj(k.content).text))}</p>
                <small>{str(k.visibility) === 'common' ? '공통 지식' : '범위 지정 지식'}</small>
              </button>
            ))}
          </div>
        </QueryState>
        <More query={q} />
      </Panel>
      {open && (
        <KnowledgeDialog
          key={str(open.id, 'new')}
          initial={open}
          onClose={() => setOpen(null)}
          onSaved={(r) => {
            setState(str(r.state, 'draft'));
            setOpen(r);
          }}
        />
      )}
    </div>
  );
}
function KnowledgeDialog({
  initial,
  onClose,
  onSaved,
}: {
  initial: Row;
  onClose: () => void;
  onSaved: (r: Row) => void;
}) {
  const existing = !!initial.knowledge_id,
    path = `/knowledge/${str(initial.knowledge_id)}/revisions/${num(initial.revision)}`,
    q = useResource(existing ? path : null),
    cmd = useCommand(),
    app = useApp();
  const row = q.data || initial;
  const [editing, setEditing] = useState(!existing),
    [revision, setRevision] = useState(false),
    [title, setTitle] = useState(str(obj(initial.content).title)),
    [text, setText] = useState(str(obj(initial.content).text)),
    [key, setKey] = useState(''),
    [kind, setKind] = useState(str(initial.kind, 'runbook')),
    [visibility, setVisibility] = useState(str(initial.visibility, 'common')),
    [refs, setRefs] = useState(strings(initial.source_refs).join('\n')),
    [compatibility, setCompatibility] = useState(
      JSON.stringify(initial.compatibility || {}, null, 2),
    ),
    [action, setAction] = useState(''),
    [comment, setComment] = useState('');
  const edit = (isRevision: boolean) => {
    setRevision(isRevision);
    setTitle(str(obj(row.content).title));
    setText(str(obj(row.content).text));
    setRefs(strings(row.source_refs).join('\n'));
    setCompatibility(JSON.stringify(row.compatibility || {}, null, 2));
    setVisibility(str(row.visibility, 'common'));
    setEditing(true);
    cmd.setError('');
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const parsed = JSON.parse(compatibility);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object')
        throw new Error('호환 조건은 JSON 객체여야 합니다.');
      const body = {
        content: { ...obj(row.content), title: title.trim(), text: text.trim() },
        compatibility: parsed,
        source_refs: refs
          .split('\n')
          .map((v) => v.trim())
          .filter(Boolean),
        visibility,
        ...(visibility === 'scoped'
          ? { scope: existing && row.scope ? row.scope : app.scope }
          : {}),
      };
      const result = await cmd.run(
        !existing
          ? '/knowledge'
          : revision
            ? `/knowledge/${str(row.knowledge_id)}/revisions`
            : path,
        { ...body, ...(!existing ? { knowledge_key: key.trim(), kind } : {}) },
        {
          method: existing && !revision ? 'PATCH' : 'POST',
          version: existing && !revision ? num(row.version) : undefined,
        },
      );
      if (result) {
        setEditing(false);
        setRevision(false);
        onSaved(result);
        app.notify('지식을 서버에 저장했습니다.');
      }
    } catch (e) {
      cmd.setError(e instanceof Error ? e.message : '입력값을 확인해 주세요.');
    }
  };
  const transition = async (e: FormEvent) => {
    e.preventDefault();
    const endpoint = action === 'publish' || action === 'retire' ? action : 'review';
    const body =
      action === 'publish'
        ? {}
        : action === 'retire'
          ? { reason: comment.trim() }
          : { action, comment: comment.trim() };
    const result = await cmd.run(`${path}/${endpoint}`, body, { version: num(row.version) });
    if (result) {
      setAction('');
      setComment('');
      onSaved(result);
      app.notify('서버에 상태 변경을 저장했습니다.');
    }
  };
  const content = (
    <div className="stack">
      <Badge status={str(row.state, 'draft')} />
      {editing ? (
        <form className="stack" onSubmit={save}>
          {!existing && (
            <div className="form-grid">
              <Field label="지식 고유 키">
                <input
                  required
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="예: gpu-xid-troubleshooting"
                />
              </Field>
              <Field label="종류">
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  {['runbook', 'policy', 'data_dictionary', 'reference', 'case'].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label="제목">
            <input
              required
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field label="내용">
            <textarea
              required
              rows={8}
              maxLength={16000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <Field label="공개 범위">
            <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
              <option value="common">공통 지식</option>
              <option value="scoped">선택한 관측 범위</option>
            </select>
          </Field>
          <Field
            label="근거 ID"
            hint="실제 저장된 근거 ID를 한 줄에 하나씩 입력하세요. 공통 지식에는 범위별 근거를 연결할 수 없습니다."
          >
            <textarea rows={2} value={refs} onChange={(e) => setRefs(e.target.value)} />
          </Field>
          <details>
            <summary>호환 조건</summary>
            <Field label="호환 조건 (JSON)">
              <textarea
                rows={4}
                value={compatibility}
                onChange={(e) => setCompatibility(e.target.value)}
              />
            </Field>
          </details>
          {existing && <Notice>변경 사항은 새 검토가 필요한 초안으로 저장됩니다.</Notice>}
          <CommandError error={cmd.error} />
          <div className="form-actions">
            {existing && (
              <button type="button" className="button" onClick={() => setEditing(false)}>
                편집 취소
              </button>
            )}
            <button className="button primary" disabled={cmd.busy || !title.trim() || !text.trim()}>
              {cmd.busy ? '저장 중…' : revision ? '새 revision 저장' : '초안 저장'}
            </button>
          </div>
        </form>
      ) : (
        <>
          <small>
            revision {num(row.revision)} · {str(row.knowledge_id)}
          </small>
          <RunbookContent value={row.content} />
          <details>
            <summary>범위·호환 조건·근거</summary>
            <DataView
              value={{
                visibility: row.visibility,
                scope: row.scope,
                compatibility: row.compatibility,
                source_refs: row.source_refs,
              }}
            />
          </details>
          {app.canKnowledge && (
            <div className="head-actions">
              {!['published', 'retired'].includes(str(row.state)) && (
                <button className="button" onClick={() => edit(false)}>
                  편집
                </button>
              )}
              {['published', 'retired'].includes(str(row.state)) && (
                <button className="button" onClick={() => edit(true)}>
                  새 revision 작성
                </button>
              )}
              {(row.state === 'draft'
                ? [['request', '검토 요청']]
                : row.state === 'in_review'
                  ? [
                      ['approve', '검토 승인'],
                      ['request_changes', '수정 요청'],
                    ]
                  : row.state === 'reviewed'
                    ? [['publish', '발행']]
                    : row.state === 'published'
                      ? [['retire', '폐기']]
                      : []
              ).map(([v, l]) => (
                <button
                  className="button primary"
                  key={v}
                  onClick={() => {
                    setAction(v);
                    setComment('');
                    cmd.setError('');
                  }}
                >
                  {l}
                </button>
              ))}
            </div>
          )}
          {action && (
            <form className="stack" onSubmit={transition}>
              <Notice>
                {action === 'publish'
                  ? '검토된 이 revision을 발행합니다.'
                  : '변경 사유 또는 검토 의견을 남겨 주세요.'}
              </Notice>
              {action !== 'publish' && (
                <Field label="검토 의견·사유">
                  <textarea required value={comment} onChange={(e) => setComment(e.target.value)} />
                </Field>
              )}
              <CommandError error={cmd.error} />
              <div className="form-actions">
                <button type="button" className="button" onClick={() => setAction('')}>
                  돌아가기
                </button>
                <button className="button primary" disabled={cmd.busy}>
                  {cmd.busy ? '처리 중…' : '상태 변경 적용'}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </div>
  );
  return (
    <Modal
      wide
      title={existing ? '지식 상세' : '새 지식 작성'}
      onClose={() => {
        if (!cmd.busy) onClose();
      }}
      confirmClose={
        editing && (title || text)
          ? '작성 중인 내용이 있습니다. 닫으면 저장되지 않습니다.'
          : undefined
      }
    >
      {existing ? <QueryState query={q}>{content}</QueryState> : content}
    </Modal>
  );
}
