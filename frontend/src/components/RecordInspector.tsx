import { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { errorText, useResource } from '../lib/live';
import { relationMismatch, type Relation } from '../lib/debug';
import { AlarmIdentity, DataView } from './live';
import { Notice } from './ui';
import { RunbookContent } from './RunbookContent';
import { RawRecord } from './TraceView';

export function RecordInspector({
  relation,
  onClose,
}: {
  relation: Relation;
  onClose: () => void;
}) {
  const query = useResource(relation.path || null);
  const record = relation.path ? query.data : relation.record;
  const mismatch = record ? relationMismatch(record, relation.expected) : [];
  const title = useRef<HTMLHeadingElement>(null);
  const location = useLocation();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    title.current?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, [relation.title, relation.value]);
  return (
    <aside className="record-inspector stack" aria-label="DB 연결 정보">
      <div className="panel-head">
        <h2 ref={title} tabIndex={-1}>
          {relation.title}
        </h2>
        <button className="button" onClick={onClose} aria-label="연결 정보 닫기">
          닫기
        </button>
      </div>
      <code className="record-key">{relation.value}</code>
      <dl className="live-details">
        <div>
          <dt>출처 테이블·필드</dt>
          <dd>
            <code>{relation.source}</code>
          </dd>
        </div>
        <div>
          <dt>연결 조건</dt>
          <dd>
            <code>{relation.join}</code>
          </dd>
        </div>
        <div>
          <dt>사용 목적</dt>
          <dd>{relation.purpose}</dd>
        </div>
      </dl>
      <Notice>{relation.note}</Notice>
      {relation.unavailable ? (
        <p role="status">{relation.unavailable}</p>
      ) : relation.path && query.isPending ? (
        <p role="status">연결 기록 조회 중…</p>
      ) : relation.path && query.isError ? (
        <div role="alert">
          <p>
            {query.error instanceof ApiError && query.error.status === 404
              ? '참조 대상 조회 결과: 찾을 수 없음'
              : '연결 기록 조회 실패'}
          </p>
          <p>{errorText(query.error)}</p>
          <button className="button" onClick={() => query.refetch()}>
            연결 기록 다시 조회
          </button>
        </div>
      ) : mismatch.length ? (
        <p role="alert">
          연결 불일치: {mismatch.join(', ')}. 다른 기록을 현재 작업의 근거로 표시하지 않습니다.
        </p>
      ) : record ? (
        <>
          <h3>
            {relation.path ? '연결 조건 확인 · API 조회 기록' : '현재 API 응답에 포함된 기록'}
          </h3>
          {relation.path?.startsWith('/incidents/') && <AlarmIdentity record={record} />}
          <DataView
            value={
              relation.path?.startsWith('/knowledge/')
                ? Object.fromEntries(Object.entries(record).filter(([key]) => key !== 'content'))
                : record
            }
            fieldNames={{ ended_at: '종료 시각' }}
          />
          {relation.path?.startsWith('/knowledge/') && <RunbookContent value={record.content} />}
          <RawRecord value={record} />
        </>
      ) : (
        <p>조회할 기록이 제공되지 않았습니다.</p>
      )}
      {relation.href && !mismatch.length && (
        <Link
          className="button"
          to={relation.href}
          state={{ from: location.pathname + location.search }}
        >
          관련 상세로 이동
        </Link>
      )}
    </aside>
  );
}
