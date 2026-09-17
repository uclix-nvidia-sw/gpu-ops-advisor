import { ArrowUpRight, BookOpen, FileCode2, Plus } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Badge, Empty, Field, Modal, Notice, PageHead, Panel, SearchBox } from '../components/ui';
import { useApp, useDatabase } from '../lib/store';
import type { Knowledge as KnowledgeType } from '../lib/types';
export function Knowledge() {
  const { db, mutate } = useDatabase();
  const app = useApp();
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState('published');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [edit, setEdit] = useState<KnowledgeType | null>(null);
  const [error, setError] = useState('');
  const [comment, setComment] = useState('');
  const [transition, setTransition] = useState('');
  const selected = db?.knowledge.find(
    (k) =>
      k.id === params.get('item') &&
      (!params.get('revision') || String(k.revision) === params.get('revision')),
  );
  const manager = app.role === 'knowledge';
  const rows =
    db?.knowledge.filter(
      (k) =>
        (tab === 'manage' || k.status === 'published') &&
        (filter === 'all' || k.kind === filter) &&
        `${k.title} ${k.content}`.toLowerCase().includes(search.toLowerCase()),
    ) || [];
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (!edit?.title.trim() || !edit.content.trim())
        throw new Error('제목과 내용을 입력해 주세요.');
      await mutate((d) => {
        const existing = d.knowledge.find((k) => k.id === edit.id && k.revision === edit.revision);
        if (existing) {
          if (existing.version !== edit.version)
            throw new Error('최신 버전과 충돌합니다. 입력을 복사한 뒤 최신본과 비교해 주세요.');
          if (existing.status === 'published' || existing.status === 'retired')
            throw new Error('발행·폐기된 revision은 직접 수정할 수 없습니다.');
          Object.assign(existing, { ...edit, status: 'draft', version: existing.version + 1 });
        } else d.knowledge.push(edit);
      });
      setEdit(null);
      app.notify('지식 초안이 저장되었습니다. 편집된 내용은 새 검토가 필요합니다.');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const change = async (e: React.FormEvent) => {
    e.preventDefault();
    await mutate((d) => {
      const k = d.knowledge.find(
        (k) => k.id === selected!.id && k.revision === selected!.revision,
      )!;
      k.status = transition;
      k.version++;
      (k.history ||= []).push({
        status: transition,
        comment,
        author: '김운영',
        at: new Date().toISOString(),
      });
    });
    setTransition('');
    app.notify('지식 상태가 변경되었습니다. 이전 결과의 revision 인용은 유지됩니다.');
  };
  return (
    <div className="page">
      <PageHead
        eyebrow="KNOWLEDGE BASE"
        title="지식·Runbook"
        description="검증된 지식과 점검 절차를 근거로, 일관된 운영 판단을 이어갑니다."
        actions={
          manager && (
            <button
              className="button primary"
              onClick={() => {
                setError('');
                setEdit({
                  id: crypto.randomUUID(),
                  title: '',
                  kind: 'Runbook',
                  revision: 1,
                  status: 'draft',
                  content: '',
                  compatibility: 'CPC-1 / CPC-2',
                  source: '',
                  version: 1,
                });
              }}
            >
              <Plus size={16} />
              지식 초안 작성
            </button>
          )
        }
      />
      <div className="tabs">
        <button className={tab === 'published' ? 'active' : ''} onClick={() => setTab('published')}>
          발행 지식
        </button>
        <button
          className={tab === 'procedures' ? 'active' : ''}
          onClick={() => setTab('procedures')}
        >
          등록 조사 절차
        </button>
        {manager && (
          <button className={tab === 'manage' ? 'active' : ''} onClick={() => setTab('manage')}>
            지식 관리
          </button>
        )}
      </div>
      {tab === 'procedures' ? (
        <>
          <Notice>
            조사 절차는 등록된 코드가 원본입니다. 이 화면에서는 입력·조회·종료 규칙을 읽을 수
            있습니다.
          </Notice>
          <Panel title="등록 절차">
            <div className="readiness-grid">
              {[
                [
                  'gpu_xid_investigation',
                  'GPU Xid 오류 조사',
                  'GPU UUID·오류 코드·사건 시각',
                  '오류 로그→관계→영향 · 근거 부족 시 종료',
                ],
                [
                  'pod_gpu_relation',
                  'Pod GPU 관계 확인',
                  'CPC·Namespace·Pod UID·시각',
                  '동시점 매핑 조회 · 식별 불명확 시 보류',
                ],
                [
                  'post_action_observation',
                  '조치 후 관측',
                  '실제 조치 기록·후속 관측 기간',
                  '장비 회복·업무 복구 독립 확인',
                ],
              ].map((r) => (
                <div className="readiness-item" key={r[0]}>
                  <FileCode2 size={22} />
                  <div>
                    <h3>{r[1]}</h3>
                    <p className="mono">{r[0]} · v1.1</p>
                    <p>
                      입력: {r[2]}
                      <br />
                      종료 규칙: {r[3]}
                    </p>
                  </div>
                  <Badge status="neutral" label="읽기 전용" />
                </div>
              ))}
            </div>
          </Panel>
        </>
      ) : (
        <>
          <div className="toolbar">
            <SearchBox
              value={search}
              onChange={setSearch}
              placeholder="오류 코드, 증상 또는 지식 검색"
            />
            <select
              aria-label="지식 종류"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">모든 종류</option>
              {['Runbook', '정책', '데이터 의미', '참고 근거', '검증 사례'].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <span className="toolbar-count">{rows.length}개 지식</span>
          </div>
          <div className="knowledge-grid">
            {rows.map((k) => (
              <button
                className="knowledge-card"
                key={`${k.id}-${k.revision}`}
                onClick={() => setParams({ item: k.id, revision: String(k.revision) })}
              >
                <div className="knowledge-top">
                  <span className="topic-icon green">
                    <BookOpen size={22} />
                  </span>
                  <Badge status={k.status} />
                </div>
                <span className="eyebrow">
                  {k.kind.toUpperCase()} · REVISION {k.revision}
                </span>
                <h2>{k.title}</h2>
                <p>{k.content}</p>
                <div className="knowledge-footer">
                  <span>{k.compatibility}</span>
                  <ArrowUpRight size={17} />
                </div>
              </button>
            ))}
          </div>
          {!rows.length && <Empty />}
        </>
      )}
      {selected && (manager || ['published', 'retired'].includes(selected.status)) && (
        <Modal title={selected.title} onClose={() => setParams({})} wide>
          <div className="stack">
            <div className="inline-states">
              <Badge status={selected.status} />
              <span>
                {selected.kind} · revision {selected.revision}
              </span>
            </div>
            <dl className="details">
              <dt>호환 조건</dt>
              <dd>{selected.compatibility}</dd>
              <dt>근거·출처</dt>
              <dd>{selected.source}</dd>
              <dt>공개 범위</dt>
              <dd>CPC-1 / CPC-2 · 데모</dd>
              <dt>필수 근거</dt>
              <dd>대상 UUID·사건 시각·원본 관측</dd>
            </dl>
            <div className="knowledge-content">{selected.content}</div>
            {!!selected.history?.length && (
              <details>
                <summary>검토·발행 이력</summary>
                <div className="stack advanced-fields">
                  {selected.history.map((h, i) => (
                    <div className="review-record" key={i}>
                      <Badge status={h.status} />
                      <p>{h.comment}</p>
                      <small>
                        {h.author} · {h.at}
                      </small>
                    </div>
                  ))}
                </div>
              </details>
            )}
            {selected.status === 'retired' && (
              <Notice tone="warning">
                폐기된 revision입니다. 과거 인용을 위해 열람할 수 있으며 새 조사 추천에서
                제외됩니다.
              </Notice>
            )}
            {manager && (
              <div className="form-actions">
                {!['published', 'retired'].includes(selected.status) && (
                  <button
                    className="button"
                    onClick={() => {
                      setEdit({ ...selected });
                      setError('');
                    }}
                  >
                    초안 편집
                  </button>
                )}
                {selected.status === 'draft' && (
                  <button
                    className="button primary"
                    onClick={() => {
                      setTransition('in_review');
                      setComment('');
                    }}
                  >
                    검토 요청
                  </button>
                )}
                {selected.status === 'in_review' && (
                  <>
                    <button className="button" onClick={() => setTransition('draft')}>
                      수정 요청
                    </button>
                    <button className="button primary" onClick={() => setTransition('reviewed')}>
                      검토 승인
                    </button>
                  </>
                )}
                {selected.status === 'reviewed' && (
                  <button className="button primary" onClick={() => setTransition('published')}>
                    발행
                  </button>
                )}
                {selected.status === 'published' && (
                  <>
                    <button
                      className="button"
                      onClick={() => {
                        setEdit({
                          ...selected,
                          revision:
                            Math.max(
                              ...db!.knowledge
                                .filter((k) => k.id === selected.id)
                                .map((k) => k.revision),
                            ) + 1,
                          version: 1,
                          status: 'draft',
                        });
                        setError('');
                      }}
                    >
                      새 revision 초안
                    </button>
                    <button className="button danger" onClick={() => setTransition('retired')}>
                      발행본 폐기
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
      {edit && (
        <Modal
          title="지식 초안 편집"
          onClose={() => setEdit(null)}
          confirmClose="초안 편집을 닫을까요? 저장하지 않은 변경은 사라집니다."
          wide
        >
          <form className="stack" onSubmit={save}>
            <Field label="제목 *">
              <input
                required
                value={edit.title}
                onChange={(e) => setEdit({ ...edit, title: e.target.value })}
              />
            </Field>
            <Field label="종류">
              <select
                value={edit.kind}
                onChange={(e) => setEdit({ ...edit, kind: e.target.value })}
              >
                {['Runbook', '정책', '데이터 의미', '참고 근거', '검증 사례'].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </Field>
            <Field label="내용 *">
              <textarea
                required
                rows={7}
                value={edit.content}
                onChange={(e) => setEdit({ ...edit, content: e.target.value })}
              />
            </Field>
            <Field label="호환·지원 조건 *">
              <input
                required
                value={edit.compatibility}
                onChange={(e) => setEdit({ ...edit, compatibility: e.target.value })}
              />
            </Field>
            <Field label="근거·출처 *">
              <input
                required
                value={edit.source}
                onChange={(e) => setEdit({ ...edit, source: e.target.value })}
              />
            </Field>
            <Notice>
              검토된 내용을 편집하면 초안 상태로 돌아갑니다. 발행본은 직접 수정하지 않습니다.
            </Notice>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary">초안 저장</button>
          </form>
        </Modal>
      )}
      {transition && (
        <Modal title="지식 상태 변경" onClose={() => setTransition('')}>
          <form className="stack" onSubmit={change}>
            <Notice>
              대상 revision {selected?.revision} · 변경 상태 {transition}
            </Notice>
            <Field label="검토 의견 / 변경 사유 *">
              <textarea required value={comment} onChange={(e) => setComment(e.target.value)} />
            </Field>
            <button className="button primary" disabled={!comment.trim()}>
              변경 저장
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
