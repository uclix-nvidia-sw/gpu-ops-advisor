import { obj, rows, str, type Row } from '../lib/live';
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
  // Historical prose can contain generated critic status. Keep stored originals intact.
  const narrative = rows(result.narrative).map((section) =>
    section.id === 'limits'
      ? {
          ...section,
          title: '수집·작성 상세',
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
  const sources = rows(obj(obj(result.quality).report).source_items);
  const paragraphs = (id: string) =>
    narrative
      .filter((s) => s.id === id)
      .flatMap((s) => str(s.text).split(/\n\s*\n/))
      .filter(Boolean);
  const ids = [
    ...new Set(
      narrative.flatMap(
        (s) => str(s.text).match(/GPU-[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}/gi) || [],
      ),
    ),
  ];
  const readable = (text: string) =>
    text.replace(
      /GPU-[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}/gi,
      (id) => `GPU ${ids.indexOf(id) + 1} (보고서 표기)`,
    );
  return (
    <section
      id="final-report"
      className="rca-narrative rca-operator-report"
      aria-label="RCA 최종 보고서"
    >
      <header className="rca-narrative-header">
        <h3>RCA 장애 보고서</h3>
        <p>사건 · 관측 결과 · 권고 조치 · 반복 이력</p>
      </header>
      <RcaIncidentSummary result={result} />
      <section className="rca-narrative-section">
        <h4>2. 분석 결과와 권고 조치</h4>
        <h5>사건별 분석</h5>
        {paragraphs('cause').map((text, i) => (
          <p key={i}>{readable(text)}</p>
        ))}
        <h5>런북 권고 조치</h5>
        <ol className="rca-action-list">
          {paragraphs('action')
            .slice(0, 3)
            .map((text, i) => (
              <li key={i}>{readable(text)}</li>
            ))}
        </ol>
        {paragraphs('action').length > 3 && (
          <details>
            <summary>적용 환경·참고 지침</summary>
            {paragraphs('action')
              .slice(3)
              .map((text, i) => (
                <p key={i}>{readable(text)}</p>
              ))}
          </details>
        )}
        {ids.length > 0 && (
          <details>
            <summary>보고서 GPU 표기와 실제 식별자</summary>
            {ids.map((id, i) => (
              <p key={id}>
                GPU {i + 1}: {id}
              </p>
            ))}
          </details>
        )}
      </section>
      <RcaTriageObservations result={result} onEvidence={onEvidence} />
      <RcaHostHistory result={result} />
      <section className="rca-narrative-section">
        <h4>5. 조사·비교 원문과 처리 상세</h4>
        {narrative
          .filter((s) => !['cause', 'action'].includes(str(s.id)) && str(s.text).trim())
          .map((s, i) => {
            const raw = sources.filter((r) => r.section === s.id && r.detail_only === true);
            const text = raw
              .reduce((value, r) => value.replace(str(r.text), ''), str(s.text))
              .trim();
            return (
              <section key={i}>
                <h5>{str(s.title)}</h5>
                {text && <p style={{ whiteSpace: 'pre-wrap' }}>{text}</p>}
                {raw.length > 0 && (
                  <details>
                    <summary>수집 데이터 원문·집계</summary>
                    {raw.map((r, j) => (
                      <p key={j} style={{ whiteSpace: 'pre-wrap' }}>
                        {str(r.text)}
                      </p>
                    ))}
                  </details>
                )}
              </section>
            );
          })}
        <details>
          <summary>저장된 분석·권고 원문</summary>
          {narrative
            .filter((s) => ['cause', 'action'].includes(str(s.id)))
            .map((s, i) => (
              <p key={i} style={{ whiteSpace: 'pre-wrap' }}>
                {str(s.text)}
              </p>
            ))}
        </details>
        <p>
          보고서 작성 상태:{' '}
          {str(obj(obj(result.quality).report).status) ||
            str(result.narrative_status) ||
            '저장 결과 기준'}
        </p>
      </section>
    </section>
  );
}
