import { RcaGuidance } from './RcaGuidance';
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
// Keep historical model text available while separating identity limits from causes.
function CauseExplanation({ paragraphs, result }: { paragraphs: string[]; result: Row }) {
  const xid79 = rows(result.runbook_revisions).some((r) => r.knowledge_key === 'RB-XID-79');
  const hasCatalog = rows(result.narrative).some(
    (s) => s.id === 'guidance' && /GPU has fallen off the bus/.test(str(s.text)),
  );
  const identityClaims = paragraphs.filter((p) => /장치 식별 불확실성.{0,20}원인/.test(p));
  const mismatch = rows(result.device_observations).some(
    (o) => o.pci_inventory_relation === 'not_in_reported_inventory',
  );
  return (
    <>
      {xid79 && hasCatalog && (
        <p>
          <strong>일반적인 원인 후보: </strong>GPU의 물리적인 연결 이탈이나 PCIe 연결 불량을 검토할
          수 있습니다. XID79 로그가 반복되더라도 같은 오류의 재보고일 수 있으므로 반복 장애나 물리적
          분리의 증거로 단정하지 않습니다. 시험 주입 여부와 실제 장치의 접근 상태를 먼저 확인해야
          합니다.
        </p>
      )}
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
            아래 원문은 장치 식별의 불확실성을 원인처럼 표현했습니다. 분석 한계로 읽어야 하며,
            저장된 결과는 변경하지 않았습니다.
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
            {str(section.id) === 'guidance'
              ? '다음에 확인할 내용'
              : str(section.title) || '분석 설명'}
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
              <h4 id={`rca-report-title-${index}`}>
                {str(section.id) === 'guidance'
                  ? '다음에 확인할 내용'
                  : str(section.title) || '분석 설명'}
              </h4>
              {str(section.id) === 'problem' &&
                rows(result.runbook_revisions).some((r) => r.knowledge_key === 'RB-SXID-11001') &&
                rows(result.narrative).some(
                  (s) => s.id === 'guidance' && /ingress invalid command/.test(str(s.text)),
                ) && (
                  <p>
                    <strong>오류 의미: </strong>SXID11001은 NVSwitch의 수신 측에서 잘못된 명령을
                    감지했다는 보고입니다. 어느 스위치·포트에서 발생했는지 확인해야 하며 GPU
                    고장이나 전체 서버 장애를 뜻한다고 단정할 수는 없습니다.
                  </p>
                )}
              {str(section.id) === 'guidance' ? (
                <RcaGuidance paragraphs={paragraphs} result={result} />
              ) : str(section.id) === 'cause' ? (
                <CauseExplanation paragraphs={paragraphs} result={result} />
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
