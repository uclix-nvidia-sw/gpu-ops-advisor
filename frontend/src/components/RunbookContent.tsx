import { DataView } from './live';
import { obj, str } from '../lib/live';

const fields: Record<string, string> = {
  description: '코드·증상 설명',
  text: '본문',
  claim: '판단 내용',
  classification: '분류',
  search: '대상 오류 코드·검색어',
  codes: '오류 코드',
  aliases: '별칭',
  required_evidence: '판단에 필요한 근거',
  applicability_conditions: '적용 조건',
  exclusion_conditions: '제외 조건',
  required_queries: '필수 조사 쿼리',
  observation_plan: '관측 계획',
  recommendations: '검토할 조치',
  sources: '출처',
  analysis_guidance: '분석 가이드',
  limitations: '판단 한계',
  investigation_only: '조사 전용',
};
export function RunbookContent({ value }: { value: unknown }) {
  const content = obj(value);
  const order = Object.keys(fields);
  const entries = Object.entries(content)
    .filter(([k]) => !['title', 'schema'].includes(k))
    .sort(
      ([a], [b]) =>
        (order.includes(a) ? order.indexOf(a) : order.length) -
        (order.includes(b) ? order.indexOf(b) : order.length),
    );
  return (
    <section className="stack runbook-content" aria-label="Runbook 본문">
      <h3>{str(content.title, '지식 본문')}</h3>
      {str(content.schema) && <small>{str(content.schema)}</small>}
      {entries.length ? (
        entries.map(([key, data]) => (
          <section key={key}>
            <h4>{fields[key] || key}</h4>
            <DataView value={data} fieldNames={fields} />
          </section>
        ))
      ) : (
        <p>저장된 본문이 없습니다.</p>
      )}
      <details>
        <summary>content 원본 JSON</summary>
        <pre className="trace-json">{JSON.stringify(value ?? null, null, 2)}</pre>
      </details>
    </section>
  );
}
