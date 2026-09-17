import { ArrowUp, FileChartColumn, Maximize2, Plus, ScanSearch, Sparkles, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { scopeLabel } from '../lib/domain';
import { useApp, useDatabase } from '../lib/store';
export function Assistant({ full = false }: { full?: boolean }) {
  const app = useApp();
  const { db, mutate } = useDatabase();
  const params = useParams();
  const location = useLocation();
  const [conversation, setConversation] = useState(
    () =>
      (full ? params.id : undefined) ||
      sessionStorage.getItem('dsx-conversation') ||
      'demo-conversation',
  );
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(app.assistantContext.startsWith('일반') ? 'general' : 'screen');
  const scroll = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 760px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)');
    const update = () => setMobile(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const messages = db?.messages[conversation] || [];
  useEffect(() => {
    sessionStorage.setItem('dsx-conversation', conversation);
  }, [conversation]);
  useEffect(() => {
    scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'instant' });
  }, [messages.length, busy]);
  useEffect(() => {
    if (full) return;
    const prior = document.activeElement as HTMLElement;
    if (mobile) dialog.current?.showModal();
    close.current?.focus();
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') app.setAssistant(false);
    };
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('keydown', escape);
      dialog.current?.close();
      requestAnimationFrame(() => {
        if (prior?.isConnected && prior.tagName !== 'BODY') prior.focus();
        else document.querySelector<HTMLButtonElement>('.assistant-toggle')?.focus();
      });
    };
  }, [full, mobile]);
  const submit = async (value = text) => {
    if (!value.trim() || busy) return;
    setBusy(true);
    const context =
      mode === 'general'
        ? '일반 질문 · 운영 데이터 참조 없음'
        : mode === 'all'
          ? scopeLabel(app.scope)
          : `${app.assistantContext.startsWith('일반') ? scopeLabel(app.scope) : app.assistantContext} · ${location.pathname} · ${app.period}`;
    const fixedScope = structuredClone(app.scope);
    await new Promise((r) => setTimeout(r, 450));
    await mutate((d) => {
      (d.messages[conversation] ||= []).push({
        id: crypto.randomUUID(),
        text: value.trim(),
        context,
        scope: fixedScope,
        created_at: new Date().toISOString(),
        response:
          mode === 'general'
            ? 'GPU 운영에서는 장비 상태와 관측 데이터의 품질을 함께 살펴봅니다. GPU 활동과 VRAM 점유는 서로 다른 지표이며, 누락된 관측을 정상 또는 0으로 해석해서는 안 됩니다.\n\n긴 원인 조사나 기간 집계가 필요하면 아래에서 조사 또는 보고서 조건을 설정할 수 있습니다.'
            : `선택한 맥락을 확인했습니다. ${context}\n\n이 데모에서는 dgx-03의 Xid 79 오류와 dgx-08의 수신 지연이 서로 다른 검토 항목입니다. 오류 근거와 당시 GPU·Pod 관계를 먼저 확인하고, 장비 회복과 업무 복구를 따로 검토해 주세요.\n\n실제 데이터 조회나 모델 추론을 실행한 답변이 아닌 화면 검증용 예시 응답입니다.`,
      });
    });
    setText('');
    setBusy(false);
  };
  const content = (
    <aside
      className={`assistant-panel ${full ? 'assistant-full' : ''}`}
      aria-label="공통 Assistant"
    >
      <header className="assistant-header">
        <span className="ai-icon">
          <Sparkles size={18} />
        </span>
        <div>
          <h2>DSX Assistant</h2>
          <small>운영을 이해하는 또 하나의 시선</small>
        </div>
        <button
          className="icon-button"
          aria-label="새 대화"
          onClick={() => {
            setConversation(crypto.randomUUID());
            setText('');
          }}
        >
          <Plus size={18} />
        </button>
        {!full && (
          <Link
            aria-label="대화 펼치기"
            className="icon-button"
            to={`/conversations/${conversation}`}
          >
            <Maximize2 size={16} />
          </Link>
        )}
        <button
          ref={close}
          className="icon-button"
          aria-label="Assistant 닫기"
          onClick={() => app.setAssistant(false)}
          style={full ? { display: 'none' } : {}}
        >
          <X size={18} />
        </button>
      </header>
      <div className="assistant-context">
        <select
          aria-label="Assistant 질문 범위"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="general">일반 질문</option>
          <option value="screen">현재 화면</option>
          <option value="all">접근 가능한 전체 범위</option>
        </select>
        <p>{mode === 'general' ? '운영 데이터 참조 없음' : scopeLabel(app.scope)}</p>
        {mode === 'screen' && (
          <button
            className="text-button"
            onClick={() => app.ask(`${location.pathname} · ${app.period} · 2026.09.16 14:15 KST`)}
          >
            현재 화면 범위 적용
          </button>
        )}
      </div>
      <div className="assistant-messages" ref={scroll}>
        {!messages.length && (
          <div className="assistant-welcome">
            <span className="welcome-icon">
              <Sparkles size={26} />
            </span>
            <div className="eyebrow">YOUR OPERATIONS COPILOT</div>
            <h3>무엇을 살펴볼까요?</h3>
            <p>
              관측의 의미를 이해하고,
              <br />
              다음에 확인할 근거를 찾아보세요.
            </p>
            {[
              'GPU 활동과 VRAM 점유는 어떻게 다른가요?',
              'GPU 관계 미관측은 무엇을 의미하나요?',
              '현재 우선 검토할 항목을 알려주세요.',
            ].map((q) => (
              <button key={q} onClick={() => submit(q)}>
                {q}
                <ArrowUp size={14} />
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div className="message-pair" key={m.id}>
            <div className="user-message">{m.text}</div>
            <div className="message-context">{m.context}</div>
            <div className="assistant-message">
              <Sparkles size={17} />
              <div>
                <b>
                  DSX Assistant <span>예시 응답</span>
                </b>
                <p>{m.response}</p>
                <small>처리 주체: 데모 응답기 · 모델 호출 없음</small>
              </div>
            </div>
            <div className="message-links">
              <Link to="/fleet/quality">관측 상태 확인</Link>
              <Link to="/knowledge">관련 지식 보기</Link>
            </div>
          </div>
        ))}
        {busy && (
          <div role="status" className="thinking">
            <span />
            맥락을 확인하고 있습니다…
          </div>
        )}
      </div>
      <div className="assistant-compose">
        <div className="assistant-shortcuts">
          <Link to="/analyses/new" onClick={() => app.setAssistant(false)}>
            <ScanSearch size={14} />
            RCA 조사
          </Link>
          <Link to="/reports/new" onClick={() => app.setAssistant(false)}>
            <FileChartColumn size={14} />
            보고서 요청
          </Link>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            aria-label="Assistant 질문"
            placeholder="운영에 대해 질문하세요…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button disabled={busy || !text.trim()} className="send-button" aria-label="질문 보내기">
            <ArrowUp size={18} />
          </button>
        </form>
        <small>데모 응답 · Enter 전송 / Shift + Enter 줄바꿈</small>
      </div>
    </aside>
  );
  return mobile && !full ? (
    <dialog
      ref={dialog}
      className="assistant-dialog"
      aria-label="공통 Assistant"
      onCancel={(e) => {
        e.preventDefault();
        app.setAssistant(false);
      }}
    >
      {content}
    </dialog>
  ) : (
    content
  );
}
