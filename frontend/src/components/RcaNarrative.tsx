import { rows, str, type Row } from '../lib/live';
import './RcaNarrative.css';

// Localize only the explicitly labelled incident timestamp; preserve stored results.
function incidentTime(text: string): string {
  return text.replace(
    /(^|\n)사건 기준 시각: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))(?=\n|$)/g,
    (original, prefix: string, value: string) => {
      if (!Number.isFinite(Date.parse(value))) return original;
      const formatted = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23',
      }).format(new Date(value));
      return `${prefix}사건 기준 시각: ${formatted} KST (한국 시각)`;
    },
  );
}
export function RcaNarrative({
  result,
  consolidateChecks = false,
}: {
  result: Row;
  consolidateChecks?: boolean;
}) {
  const sections = rows(result.narrative).filter(
    (s) => !consolidateChecks || !['next', 'limits'].includes(str(s.id)),
  );
  if (!sections.length) return null;
  return (
    <section id="final-report" className="rca-narrative" aria-label="RCA 최종 보고서">
      <header className="rca-narrative-header">
        <h3>RCA 최종 보고서</h3>
        <p>무슨 문제가 보고됐는지, 원인은 무엇인지, 다음에 무엇을 해야 하는지 확인하세요.</p>
        <details className="rca-narrative-method">
          <summary>보고서 작성 방식</summary>
          <p className="muted">
            {result.narrative_status === 'complete'
              ? '확인된 내용을 LLM이 우선순위에 따라 정리했습니다.'
              : 'LLM 설명을 사용하지 못해 저장된 근거와 판단으로 기본 보고서를 작성했습니다.'}{' '}
            보고서 작성과 원인 확정은 별개입니다.
          </p>
        </details>
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
              className={`rca-narrative-section${list ? ' rca-narrative-checks' : ''}${str(section.id) === 'problem' ? ' rca-narrative-problem' : ''}`}
              aria-labelledby={`rca-report-title-${index}`}
            >
              <h4 id={`rca-report-title-${index}`}>{str(section.title) || '분석 설명'}</h4>
              {list && paragraphs.length > 0 ? (
                <>
                  <ul>
                    {paragraphs.slice(0, 2).map((text, i) => (
                      <li key={i}>{text}</li>
                    ))}
                  </ul>
                  {paragraphs.length > 2 && (
                    <details className="rca-narrative-more">
                      <summary>
                        {str(section.title)} {paragraphs.length - 2}개 더 보기
                      </summary>
                      <ul>
                        {paragraphs.slice(2).map((text, i) => (
                          <li key={i}>{text}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              ) : paragraphs.length > 0 ? (
                paragraphs.map((text, i) =>
                  str(section.id) === 'problem' && text.startsWith('대상 식별 정보') ? (
                    <details key={i}>
                      <summary>대상 연결용 식별자</summary>
                      <p>
                        아래 ID는 로그와 노드를 연결하는 식별자이며 GPU 모델명이나 고장 장치의 확정
                        정보가 아닙니다.
                      </p>
                      <p>{text}</p>
                    </details>
                  ) : (
                    <p key={i}>{str(section.id) === 'problem' ? incidentTime(text) : text}</p>
                  ),
                )
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
