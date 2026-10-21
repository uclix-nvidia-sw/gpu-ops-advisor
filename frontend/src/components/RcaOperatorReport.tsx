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
  const narrative = rows(result.narrative);
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
        {paragraphs('cause').map((text, i) => (
          <p key={i}>{readable(text)}</p>
        ))}
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
      </section>
      <RcaTriageObservations result={result} onEvidence={onEvidence} />
      <RcaHostHistory result={result} />
      <details className="rca-narrative-section">
        <summary>5. 조사·비교 원문과 처리 상세</summary>
        {narrative
          .filter((s) => !['cause', 'action'].includes(str(s.id)))
          .map((s, i) => (
            <details key={i}>
              <summary>{str(s.title)}</summary>
              <p style={{ whiteSpace: 'pre-wrap' }}>{str(s.text)}</p>
            </details>
          ))}
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
      </details>
    </section>
  );
}
