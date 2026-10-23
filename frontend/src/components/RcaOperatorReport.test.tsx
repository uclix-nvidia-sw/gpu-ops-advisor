import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaOperatorReport } from './RcaOperatorReport';

it('leads with saved facts, candidate, limits and the next check without changing the result', () => {
  const result = {
    result_status: 'partial',
    missing_inputs: ['causal_confirmation_evidence'],
    narrative: [
      { id: 'problem', text: '노드에서 오류가 보고되었습니다.' },
      { id: 'cause', text: '장치와 호스트 연결을 대조해야 합니다.' },
      { id: 'limits', text: '작업 영향은 확인하지 못했습니다.' },
      { id: 'next', text: '같은 시각의 작업 이력을 확인하세요.' },
    ],
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  for (const heading of ['확인한 사실', '원인 후보', '확인하지 못한 사항', '다음 확인'])
    expect(html.indexOf(heading)).toBeLessThan(html.indexOf('4. 분석 및 해석'));
  for (const section of result.narrative)
    expect(html.indexOf(section.text)).toBeLessThan(html.indexOf('4. 분석 및 해석'));
  expect(html).toContain('후보는 확정 원인이 아닙니다.');
  expect(html).toContain('보고된 증상만으로 실제 원인을 확정할 수 없습니다');
  expect(html).toContain('<section id="rca-response-reference"');
  expect(JSON.stringify(result)).toBe(before);
});

it('preserves additional limits and shows absent findings without a healthy assessment', () => {
  const html = renderToStaticMarkup(
    <RcaOperatorReport
      result={{ limitations: ['제한 1', '제한 2', '제한 3', '제한 4'] }}
      decisionSummary
    />,
  );
  expect(html).toContain('저장된 관측 사실을 확인할 수 없습니다');
  expect(html).toContain('저장된 원인 후보가 없습니다');
  expect(html).toContain('나머지 제한 1건');
  expect(html).toContain('제한 4');
  expect(html).not.toContain('정상 관측');
});

it('keeps every saved fact and next-check paragraph accessible after the two-item preview', () => {
  const facts = [
    '첫 번째 관측 원문',
    '두 번째 관측 원문',
    '세 번째 관측 원문',
    '네 번째 관측 원문',
  ];
  const checks = ['첫 번째 확인 원문', '두 번째 확인 원문', '세 번째 확인 원문'];
  const result = {
    narrative: [
      { id: 'problem', text: facts.join('\n\n') },
      { id: 'next', text: checks.join('\n\n') },
    ],
  };
  const original = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  const summary = html.slice(0, html.indexOf('id="rca-analysis-detail"'));
  expect(summary).toContain('<details><summary>나머지 관측 사실 2건</summary>');
  expect(summary).toContain('<details><summary>나머지 확인 제안 1건</summary>');
  for (const text of [...facts, ...checks]) expect(summary).toContain(text);
  expect(summary).toContain('href="#rca-response-reference"');
  expect(html).toContain('<section id="rca-response-reference"');
  expect(JSON.stringify(result)).toBe(original);
});

it('preserves the existing six-section report when the console summary is not requested', () => {
  const html = renderToStaticMarkup(<RcaOperatorReport result={{}} />);
  expect(html).not.toContain('aria-label="사건 판단 요약"');
  for (const heading of [
    '1. 한눈에 보기',
    '2. 대응 순서',
    '3. 관련 로그·메트릭',
    '4. 분석 및 해석',
    '5. 이전 사건 이력',
  ])
    expect(html).toContain(heading);
});
