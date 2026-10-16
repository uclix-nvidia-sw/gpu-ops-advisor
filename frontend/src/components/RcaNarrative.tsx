import { RcaEvaluation } from './RcaEvaluation';
import { structuredGuidance } from './StructuredGuidance';
import { RcaGuidance } from './RcaGuidance';
import { obj, rows, str, type Row } from '../lib/live';
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
// Keep historical model text available while separating identity limits from causes.
function CauseExplanation({
  paragraphs,
  result,
  findingsLed,
}: {
  paragraphs: string[];
  result: Row;
  findingsLed: boolean;
}) {
  const mismatch = rows(result.device_observations).some(
    (o) => o.pci_inventory_relation === 'not_in_reported_inventory',
  );
  const identityClaims = paragraphs.filter(
    (p) => /장치 식별 불확실성.{0,20}원인/.test(p) || (mismatch && /PCI.{0,40}연결된 GPU/.test(p)),
  );
  return (
    <>
      {/* Findings-led reports already state the candidates with this incident's evidence. */}
      {(findingsLed ? [] : structuredGuidance(result)).map((entry, i) => (
        <p key={i}>
          <strong>일반적인 조사 방향: </strong>
          {str((entry.guidance as Row).cause_note)}
        </p>
      ))}
      {mismatch && <p>이번 기록은 오류 장치가 식별되지 않아 해당 원인을 뒷받침하지 못합니다.</p>}
      {paragraphs
        .filter((p) => !identityClaims.includes(p))
        .map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      {mismatch && (
        <p>
          <strong>이번 판단의 제한: </strong>보고된 PCI 주소가 수집된 GPU 목록과 연결되지 않아 오류
          장치를 식별하지 못했습니다. 테스트용 오류 주입으로 생성된 로그인지도 함께 확인해야 합니다.
          이는 장애 원인이 아니라 원인을 확정하지 못하는 이유입니다.
        </p>
      )}
      {identityClaims.length > 0 && (
        <details>
          <summary>저장된 원인 문장·해석 주의</summary>
          <p>
            아래 원문에는 미확인 장치 연결 또는 식별 불확실성을 원인처럼 표현한 내용이 있습니다.
            확정된 사실로 읽지 마세요. 저장된 결과는 변경하지 않았습니다.
          </p>
          {identityClaims.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </details>
      )}
    </>
  );
}
export function RcaNarrative({
  result,
  consolidateChecks = false,
  reader = false,
}: {
  result: Row;
  consolidateChecks?: boolean;
  reader?: boolean;
}) {
  const presentation = str(obj(obj(result.quality).report).presentation);
  const materialReport = presentation === 'rca-material/1';
  const incidentFirst = presentation.startsWith('incident-first/');
  // /2: deterministic incident findings lead and the reference guidance is a primary section.
  const findingsLed = presentation === 'incident-first/2';
  const collapsed = (id: string) =>
    !reader && incidentFirst && (id === 'limits' || (id === 'guidance' && !findingsLed));
  const sections = rows(result.narrative).filter(
    (s) =>
      materialReport ||
      incidentFirst ||
      !consolidateChecks ||
      !['next', 'limits'].includes(str(s.id)),
  );
  if (!sections.length) return null;
  return (
    <section id="final-report" className="rca-narrative" aria-label="RCA 최종 보고서">
      {!reader && <RcaEvaluation result={result} />}
      <header className="rca-narrative-header">
        <h3>RCA 최종 보고서</h3>
        <p>무슨 문제가 보고됐는지, 원인은 무엇인지, 다음에 무엇을 해야 하는지 확인하세요.</p>
        <details className="rca-narrative-method">
          <summary>보고서 작성 방식</summary>
          <p className="muted">
            {result.narrative_status === 'complete'
              ? materialReport
                ? '고정된 RCA 분석 자료를 보고서 LLM이 문장으로 작성했습니다.'
                : '확인된 내용을 LLM이 우선순위에 따라 정리했습니다.'
              : 'LLM 설명을 사용하지 못해 저장된 근거와 판단으로 기본 보고서를 작성했습니다.'}{' '}
            보고서 작성과 원인 확정은 별개입니다.
          </p>
        </details>
        {materialReport && (
          <details>
            <summary>서술 전 RCA 자료와 대조</summary>
            <p>
              형식·참조 검증은 문장의 의미 일치를 보장하지 않습니다. 분석의 한계와 아래 원문을 함께
              확인하세요.
            </p>
            {rows(obj(obj(result.quality).report).source_items).map((item) => (
              <p key={str(item.id)}>{str(item.text)}</p>
            ))}
          </details>
        )}
      </header>
      {materialReport && rows(obj(result.quality).runbook_guidance).length > 0 && (
        <details className="rca-narrative-more">
          <summary>발행 Runbook 참고 안내 · 사건 분석과 구분</summary>
          <RcaGuidance paragraphs={[]} result={result} reader={reader} />
        </details>
      )}
      <nav className="rca-narrative-nav" aria-label="최종 보고서 목차">
        {sections.map((section, index) =>
          collapsed(str(section.id)) ? null : (
            <a key={index} href={`#rca-report-section-${index}`}>
              {str(section.id) === 'guidance' && !findingsLed
                ? '다음에 확인할 내용'
                : str(section.title) || '분석 설명'}
            </a>
          ),
        )}
      </nav>
      <div className="rca-narrative-sections">
        {sections.map((section, index) => {
          const paragraphs = str(section.text)
            .split(/\n\s*\n/)
            .filter((p) => p.trim());
          const list = ['next', 'limits'].includes(str(section.id));
          if (collapsed(str(section.id))) {
            return (
              <details key={index} className="rca-narrative-more">
                <summary>{str(section.title)}</summary>
                {section.id === 'guidance' ? (
                  <RcaGuidance paragraphs={paragraphs} result={result} reader={reader} />
                ) : (
                  paragraphs.map((text, i) => <p key={i}>{text}</p>)
                )}
              </details>
            );
          }
          return (
            <section
              key={index}
              id={`rca-report-section-${index}`}
              className={`rca-narrative-section${list ? ' rca-narrative-checks' : ''}${str(section.id) === 'problem' ? ' rca-narrative-problem' : ''}`}
              aria-labelledby={`rca-report-title-${index}`}
            >
              <h4 id={`rca-report-title-${index}`}>
                {str(section.id) === 'guidance' && !findingsLed
                  ? '다음에 확인할 내용'
                  : str(section.title) || '분석 설명'}
              </h4>
              {str(section.id) === 'guidance' && findingsLed ? (
                paragraphs.map((text, i) => <p key={i}>{text}</p>)
              ) : str(section.id) === 'guidance' ? (
                <RcaGuidance paragraphs={paragraphs} result={result} reader={reader} />
              ) : str(section.id) === 'cause' ? (
                <CauseExplanation
                  paragraphs={paragraphs}
                  result={result}
                  findingsLed={findingsLed}
                />
              ) : list && paragraphs.length > 0 ? (
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
                    reader ? null : (
                      <details key={i}>
                        <summary>대상 연결용 식별자</summary>
                        <p>
                          아래 ID는 로그와 노드를 연결하는 식별자이며 GPU 모델명이나 고장 장치의
                          확정 정보가 아닙니다.
                        </p>
                        <p>{text}</p>
                      </details>
                    )
                  ) : (
                    <p key={i}>
                      {str(section.id) === 'problem'
                        ? incidentTime(text).replace(
                            /\b(xid|sxid):(\d+) 보고는 확인했습니다\./gi,
                            (_, family: string, code: string) =>
                              `${family.toUpperCase()} ${code} 오류가 보고된 것을 확인했습니다.`,
                          )
                        : text}
                    </p>
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
