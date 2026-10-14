import { rows, str, type Row } from '../lib/live';
import { StructuredGuidance, structuredGuidance } from './StructuredGuidance';

// Legacy revisions remain readable without inferring error-specific instructions.
export function RcaGuidance({ paragraphs, result }: { paragraphs: string[]; result: Row }) {
  const entries = structuredGuidance(result);
  if (entries.length)
    return (
      <>
        <StructuredGuidance entries={entries} />
        <details>
          <summary>저장된 조사 지침 원문</summary>
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </details>
      </>
    );
  return (
    <>
      <details>
        <summary>적용 지침</summary>
        <p>
          {rows(result.runbook_revisions)
            .map(
              (r) =>
                `${str(r.title) || str(r.knowledge_key)} · revision ${String(r.revision ?? '?')}`,
            )
            .join(', ') || '저장된 조사 지침'}
        </p>
      </details>
      <p>
        이 결과에는 구조화된 사용자 안내가 없습니다. 아래 저장된 지침을 확인하세요. 이번 장비의 고장
        판정이나 조치 승인은 아닙니다.
      </p>
      <section aria-label="이 오류에 대한 참고 안내">
        <h5>이 오류에 대한 참고 안내</h5>
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </section>
    </>
  );
}
