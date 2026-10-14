import { obj, rows, str, type Row } from '../lib/live';

export function structuredGuidance(result: Row) {
  return rows(obj(result.quality).runbook_guidance).filter(
    (entry) => obj(entry.guidance).schema === 'gpu-rca-guidance/1.0',
  );
}

export function StructuredGuidance({ entries }: { entries: Row[] }) {
  return (
    <>
      {entries.map((entry, index) => {
        const guidance = obj(entry.guidance);
        const sources = rows(entry.sources);
        return (
          <section key={str(entry.evidence_id) || index}>
            <details>
              <summary>적용 지침</summary>
              <p>
                {str(entry.title)} · revision {String(entry.revision ?? '?')}
              </p>
            </details>
            <ol>
              {rows(guidance.next_checks).map((check, i) => (
                <li key={i}>
                  <strong>{str(check.title)}</strong>
                  <p>{str(check.text)}</p>
                </li>
              ))}
            </ol>
            <section aria-label="이 오류에 대한 참고 안내">
              <h5 className="rca-reference-heading">이 오류에 대한 참고 안내</h5>
              <p>{str(guidance.meaning)}</p>
              <p>발행된 지침의 일반 안내이며 이번 장비의 고장 판정이나 조치 승인이 아닙니다.</p>
              <dl className="rca-reference-guide">
                {rows(guidance.references).map((reference, i) => (
                  <div key={i}>
                    <dt>{str(reference.title)}</dt>
                    <dd>{str(reference.text)}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <details>
              <summary>제조사 안내·적용 조건·출처 보기</summary>
              {rows(guidance.references).map((reference, i) => (
                <section key={i}>
                  <h5>{str(reference.title)}</h5>
                  <ul>
                    {(Array.isArray(reference.source_indices) ? reference.source_indices : []).map(
                      (sourceIndex: unknown) => {
                        const source =
                          typeof sourceIndex === 'number' ? sources[sourceIndex] : undefined;
                        const url = str(source?.url);
                        return /^https?:\/\//.test(url) ? (
                          <li key={String(sourceIndex)}>
                            <a href={url} target="_blank" rel="noreferrer">
                              {str(source?.section) || '출처'}
                            </a>{' '}
                            · {str(source?.revision)}
                          </li>
                        ) : null;
                      },
                    )}
                  </ul>
                </section>
              ))}
            </details>
          </section>
        );
      })}
    </>
  );
}
