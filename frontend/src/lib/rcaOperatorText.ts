import { obj, rows, str, type Row } from './live';
import labels from './rcaLabels.json';
import { isOperatorGuidanceReference } from './rcaReferences';

// Presentation only. Raw logs, evidence IDs and the stored result remain untouched.
export function rcaOperatorText(text: string): string {
  return text
    .split('\n')
    .filter(
      (line) =>
        !/^(?:Fleet(?:·GPUd)? (?:분류|고정 정의)|수집 설정·분류 구현 출처|queries and verified bindings)/.test(
          line.trim(),
        ),
    )
    .join('\n')
    .replace(/\bD\d{2,3}\b/g, (id) =>
      id === 'D13'
        ? '보조 로그 문맥'
        : (labels.queries as Record<string, string>)[id] || '관련 자료 조회',
    );
}

export function isOperatorCollectionReference(reference: Row): boolean {
  return str(reference.title) === '수집 근거와 대응에 연결하는 방법';
}

export function operatorReportResult(result: Row): Row {
  const prose = (item: Row) => ({ ...item, text: rcaOperatorText(str(item.text)) });
  const quality = obj(result.quality);
  return {
    ...result,
    summary: rcaOperatorText(str(result.summary)),
    narrative: rows(result.narrative).map(prose),
    facts: rows(result.facts).map(prose),
    limitations: Array.isArray(result.limitations)
      ? result.limitations.map((text) => rcaOperatorText(str(text)))
      : result.limitations,
    quality: {
      ...quality,
      report: {
        ...obj(quality.report),
        source_items: rows(obj(quality.report).source_items).map(prose),
      },
      runbook_guidance: rows(quality.runbook_guidance).map((entry) => {
        const guidance = obj(entry.guidance);
        return {
          ...entry,
          guidance: {
            ...guidance,
            meaning: rcaOperatorText(str(guidance.meaning)),
            cause_note: rcaOperatorText(str(guidance.cause_note)),
            next_checks: rows(guidance.next_checks).map(prose),
            references: rows(guidance.references)
              .filter(
                (reference) =>
                  isOperatorCollectionReference(reference) ||
                  (isOperatorGuidanceReference(reference, entry.sources) &&
                    !/Fleet.*분류|GPUd.*분류|개발용|구현|수집 설정/.test(str(reference.title))),
              )
              .map(prose)
              .filter((reference) => reference.text.trim()),
          },
        };
      }),
    },
  };
}
