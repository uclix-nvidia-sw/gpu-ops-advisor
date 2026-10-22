import { obj, rows, str, strings, type Row } from '../lib/live';
import { RcaIncidentSummary } from './RcaIncidentSummary';
import { RcaTriageObservations } from './RcaTriageObservations';
import { RcaHostHistory } from './RcaHostHistory';

export function RcaOperatorReport({
  result,
  onEvidence,
}: {
  result: Row;
  onEvidence?: (id: string) => void;
}) {
  const quality = obj(result.quality);
  const narrative = rows(result.narrative).map((section) =>
    section.id === 'limits'
      ? {
          ...section,
          text: str(section.text)
            .split('\n')
            .filter(
              (line) =>
                !/^(분석 품질 검토:|조사 종료 이유:|분석 처리 상태: 독립 품질 검토|LLM 검토는 정답을|증거 의미 해석을 완료하지 못해 해석 결과는 미검토)/.test(
                  line.trim(),
                ),
            )
            .join('\n'),
        }
      : section,
  );
  const sources = rows(obj(quality.report).source_items);
  const guidance = rows(quality.runbook_guidance).filter(
    (r) => r.report_applicability !== 'reference_only',
  );
  const paragraphs = (id: string) =>
    narrative
      .filter((s) => s.id === id)
      .flatMap((s) => str(s.text).split(/\n\s*\n/))
      .filter(Boolean);
  const analysis = sources.filter(
    (r) => r.section === 'cause' && !str(r.text).startsWith('발행 Runbook의 오류 설명:'),
  );
  const refs = guidance.flatMap((g) => rows(g.sources));
  const links = (value: unknown) =>
    strings(value).map((id) =>
      onEvidence ? (
        <button className="text-link" key={id} onClick={() => onEvidence(id)}>
          근거 원문
        </button>
      ) : null,
    );
  return (
    <section
      id="final-report"
      className="rca-narrative rca-operator-report"
      aria-label="RCA 최종 보고서"
    >
      <header className="rca-narrative-header">
        <h3>RCA 장애 보고서</h3>
        <p>노드 사건 · 대응 순서 · 관측 자료 · 분석과 이력</p>
      </header>
      <RcaIncidentSummary result={result} />
      <section className="rca-narrative-section">
        <h4>2. 권고 지침</h4>
        <p>실제 조치 직전에 대상 노드와 장치 PCI 주소를 대조하세요. 조치는 운영자가 수행합니다.</p>
        {guidance.length
          ? guidance.map((g, i) => (
              <div key={i}>
                <ol className="rca-action-list">
                  {rows(obj(g.guidance).next_checks)
                    .filter((c) => !str(c.title).startsWith('알림이 가리키는'))
                    .map((c, j) => (
                      <li key={j}>
                        <strong>{str(c.title)}</strong>
                        {str(c.text)
                          .split(/(?<=다[.])\s+/)
                          .map((sentence, k) => (
                            <p key={k}>{sentence}</p>
                          ))}
                      </li>
                    ))}
                </ol>
                {links([g.evidence_id])}
              </div>
            ))
          : paragraphs('action').map((text, i) => <p key={i}>{text}</p>)}
      </section>
      <RcaTriageObservations result={result} onEvidence={onEvidence} />
      <section className="rca-narrative-section">
        <h4>4. 분석 및 해석</h4>
        {analysis.length
          ? analysis.map((r, i) => (
              <div key={i}>
                <p>{str(r.text)}</p>
                {links(r.evidence_refs)}
              </div>
            ))
          : paragraphs('cause').map((text, i) => <p key={i}>{text}</p>)}
        {paragraphs('comparison').map((text, i) => {
          const visible = sources
            .filter((r) => r.section === 'comparison' && r.detail_only === true)
            .reduce((value, r) => value.replace(str(r.text), ''), text)
            .trim();
          return visible ? <p key={i}>{visible}</p> : null;
        })}
        <RcaHostHistory result={result} embedded />
      </section>
      <section className="rca-narrative-section">
        <h4>5. 참고 자료</h4>
        <ul>
          {[...new Map(refs.map((r) => [str(r.url), r])).values()]
            .filter((r) => /^https:\/\//.test(str(r.url)))
            .map((r) => (
              <li key={str(r.url)}>
                <a href={str(r.url)} target="_blank" rel="noreferrer">
                  {str(r.section) || str(r.url)}
                </a>
              </li>
            ))}
        </ul>
        {guidance.map((g, i) => (
          <div key={i}>
            {rows(obj(g.guidance).references).map((r, j) => (
              <p key={j}>
                <strong>{str(r.title)}</strong> · {str(r.text)}
              </p>
            ))}
          </div>
        ))}
        <details>
          <summary>수집 원문·처리 상세</summary>
          {sources
            .filter((r) => r.detail_only === true)
            .map((r, i) => (
              <p key={i}>{str(r.text)}</p>
            ))}
          {narrative
            .filter((s) => !['cause', 'action', 'comparison'].includes(str(s.id)))
            .map((s, i) => (
              <section key={i}>
                <h5>{str(s.title)}</h5>
                <p style={{ whiteSpace: 'pre-wrap' }}>{str(s.text)}</p>
              </section>
            ))}
        </details>
      </section>
    </section>
  );
}
