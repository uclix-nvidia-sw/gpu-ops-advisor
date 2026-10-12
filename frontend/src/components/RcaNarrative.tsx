import { rows, str, type Row } from '../lib/live';
import './RcaNarrative.css';

// Render stored paragraphs verbatim: layout must not invent or upgrade claims.
export function RcaNarrative({ result }: { result: Row }) {
  const sections = rows(result.narrative);
  if (!sections.length) return null;
  return (
    <section id="final-report" className="rca-narrative" aria-label="RCA 최종 보고서">
      <header className="rca-narrative-header">
        <h3>RCA 최종 보고서</h3>
        <p>보고된 문제 → 원인 판단 → 권고 조건 → 추가 확인 순서로 읽어보세요.</p>
        <p className="muted">
          {result.narrative_status === 'complete'
            ? '확인된 내용을 LLM이 우선순위에 따라 정리했습니다.'
            : 'LLM 설명을 사용하지 못해 저장된 근거와 판단으로 기본 보고서를 작성했습니다.'}{' '}
          보고서 작성과 원인 확정은 별개입니다.
        </p>
      </header>
      <nav className="rca-narrative-nav" aria-label="최종 보고서 목차">
        {sections.map((section, index) => (
          <a key={index} href={`#rca-report-section-${index}`}>
            {str(section.title) || '분석 설명'}
          </a>
        ))}
      </nav>
      <div className="rca-narrative-sections">
        {sections.map((section, index) => {
          const paragraphs = str(section.text)
            .split(/\n\s*\n/)
            .filter((p) => p.trim());
          const list = ['next', 'limits'].includes(str(section.id));
          return (
            <section
              key={index}
              id={`rca-report-section-${index}`}
              className={`rca-narrative-section${list ? ' rca-narrative-checks' : ''}`}
              aria-labelledby={`rca-report-title-${index}`}
            >
              <h4 id={`rca-report-title-${index}`}>{str(section.title) || '분석 설명'}</h4>
              {list && paragraphs.length > 0 ? (
                <ul>
                  {paragraphs.map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              ) : paragraphs.length > 0 ? (
                paragraphs.map((text, i) => <p key={i}>{text}</p>)
              ) : (
                <p className="muted">이 항목에 저장된 설명이 없습니다.</p>
              )}
            </section>
          );
        })}
      </div>
    </section>
  );
}
