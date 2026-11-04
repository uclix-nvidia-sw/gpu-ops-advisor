import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { RcaNarrative } from './RcaNarrative';
import { RcaOperatorReport } from './RcaOperatorReport';
import { isOperatorReference } from '../lib/rcaReferences';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { xidDefinition } from '../lib/xidDefinition';

const root = fileURLToPath(new URL('../../../rcca-agent/runbooks', import.meta.url));
const books: Row[] = readdirSync(root, { recursive: true })
  .filter((name) => /(?:^|[/\\])RB-.*\.json$/.test(String(name)))
  .map((name) => JSON.parse(readFileSync(join(root, String(name)), 'utf8')));
const at = '2026-11-03T07:00:00Z';
const period = { start: '2026-11-03T06:30:00Z', end: '2026-11-03T07:05:00Z' };
const headings = [
  '1. 한눈에 보기',
  '2. 대응 순서',
  '3. 관련 로그·메트릭',
  '4. 분석 및 해석',
  '5. 이전 사건 이력',
  '6. 참고 자료',
];

function fixture(book: Row): Row {
  const content = obj(book.content);
  const code = str(book.knowledge_key).match(/^RB-(S?XID)-(\d+)/);
  return {
    result_status: 'partial',
    time_range: period,
    runbook_revisions: [{ knowledge_key: book.knowledge_key, revision: 1 }],
    device_observations: code
      ? []
      : [
          {
            component: strings(obj(content.search).producer_events)[0] || 'disk',
            raw_health: 'Unhealthy',
            reason:
              strings(obj(content.search).aliases)[0] ||
              'filesystem remounted as read-only due to errors',
            observed_at: at,
            target: { node: 'dgx01' },
          },
        ],
    quality: {
      ...(code
        ? {
            triage_observations: {
              schema: 'rca-triage-observations/1',
              period,
              target: {
                node: 'dgx01',
                title: `${code[1]} ${code[2]} PCI:0000:bd:00 UUID:GPU-7608a7b1-ec78-22f7-d932-8c629aed27b1`,
              },
              logs: [
                {
                  code: `${code[1]}:${code[2]}`,
                  device: 'PCI:0000:bd:00',
                  reports: 1,
                  first: at,
                  last: at,
                },
              ],
            },
          }
        : {}),
      runbook_guidance: [{ guidance: content.operator_guidance, sources: content.sources }],
    },
  };
}

it('uses all six sections for every published Runbook, with reset references inside the recovery step', () => {
  expect(books).toHaveLength(284);
  for (const book of books) {
    const result = fixture(book);
    const original = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaNarrative result={result} decisionSummary />);
    for (const heading of headings) expect(html, str(book.knowledge_key)).toContain(heading);
    expect(html).toContain('<section id="rca-glance"');
    expect(html).not.toContain('<details class="c2-rca-hardware"');
    expect(html).not.toContain('사건 대상·시각과 관련 관측 자세히 보기</summary>');
    expect(html).not.toContain('XID/SXID 오류에만');
    expect(html).not.toContain('수집 설정·분류 구현 출처');
    expect(html).not.toContain('저장 당시 오류 설명 원문');
    for (const source of rows(obj(book.content).sources)) {
      if (!isOperatorReference(source)) expect(html).not.toContain(str(source.url));
    }
    if (/^RB-S?XID-/.test(str(book.knowledge_key))) {
      const checks = rows(obj(obj(book.content).operator_guidance).next_checks).filter(
        (c) => !str(c.title).startsWith('알림이 가리키는'),
      );
      const index = checks.findIndex((c) => /^복구(?:$|[:：]| 조치)/.test(str(c.title)));
      expect(index, str(book.knowledge_key)).toBeGreaterThanOrEqual(0);
      const step = html.slice(
        html.indexOf(`id="rca-step-${index + 2}"`),
        html.indexOf(`id="rca-step-${index + 3}"`),
      );
      expect(step, str(book.knowledge_key)).toContain('<details class="rca-reset-guide">');
      expect(step).not.toContain('<details class="rca-reset-guide" open');
      expect(html.match(/class="rca-reset-guide"/g)).toHaveLength(1);
      expect(html).toContain('class="c2-rca-hardware" aria-label="장비 상세"');
    } else {
      expect(html).not.toContain('class="rca-reset-guide"');
      if (book.knowledge_key === 'RB-COMPONENT-DISK') {
        expect(html).toContain('<span class="rca-current-reason">해당 증상</span>');
        expect(html).not.toContain('▶');
      }
    }
    expect(JSON.stringify(result)).toBe(original);
  }
});

it('deduplicates matching definitions and preserves genuinely different saved explanations visibly', () => {
  const book = books.find((b) => b.knowledge_key === 'RB-XID-41')!;
  const result = fixture(book);
  const guidance = rows(obj(result.quality).runbook_guidance)[0];
  obj(guidance.guidance).meaning = xidDefinition('xid:41')!.meaning;
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  const references = html.slice(html.indexOf('id="c2-rca-references"'));
  expect(references.split(xidDefinition('xid:41')!.meaning)).toHaveLength(2);
  expect(references).not.toContain('<dt>오류 의미</dt>');
  obj(guidance.guidance).meaning = '당시 장비 세대에만 적용되는 별도 조건입니다.';
  const different = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  expect(different).toContain('조사 당시 추가 참고 설명');
  expect(different).toContain('당시 장비 세대에만 적용되는 별도 조건입니다.');
  expect(different).not.toContain('저장 당시 오류 설명 원문');
});

it.each(['rca-material/1', 'incident-first/1', 'incident-first/2', ''])(
  'retains older %s result prose inside the common six-section report',
  (presentation) => {
    const result = {
      summary: '파일시스템 오류 보고',
      quality: { report: { presentation } },
      narrative: [
        { id: 'problem', title: '증상', text: '파일시스템이 읽기 전용으로 전환되었습니다.' },
        { id: 'impact', title: '영향', text: '쓰기 작업 영향은 미확인입니다.' },
        { id: 'cause', title: '원인', text: '원인을 확정하지 못했습니다.' },
        { id: 'action', title: '조치', text: '작업 영향과 파일시스템 로그를 확인합니다.' },
        { id: 'next', title: '다음 확인', text: '디스크 상태도 확인합니다.' },
        { id: 'limits', title: '한계', text: '사용량 비교 자료가 없습니다.' },
      ],
    };
    const html = renderToStaticMarkup(<RcaNarrative result={result} decisionSummary />);
    for (const heading of headings) expect(html).toContain(heading);
    for (const section of result.narrative) expect(html).toContain(section.text);
    expect(html).not.toContain('XID/SXID 오류에만');
    expect(html).not.toContain('GPU·NVSwitch 리셋');
  },
);

it('explains query identifiers in prose, hides implementation references, and preserves the raw log and input', () => {
  const result = fixture(books.find((b) => b.knowledge_key === 'RB-XID-79')!);
  result.narrative = [
    {
      id: 'next',
      text: 'D09와 D13을 확인하세요.\n\nFleet·GPUd 분류 Fleet 고정 정의: event_type=Warning',
    },
  ];
  const q = obj(result.quality);
  rows(obj(q.triage_observations).logs)[0].message = 'NVRM raw D09 diagnostic field';
  const original = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} decisionSummary />);
  expect(html).toContain('로그·원본 이벤트와 보조 로그 문맥을 확인하세요.');
  expect(html).toContain('NVRM raw D09 diagnostic field');
  expect(html).not.toContain('event_type=Warning');
  expect(html).not.toContain('config.example.json');
  expect(html).toContain('확인할 자료와 대조 방법');
  expect(JSON.stringify(result)).toBe(original);
});

it('keeps all six sections for empty or failed results without inventing healthy observations', () => {
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{ missing_inputs: ['synthesis_failed'], result_status: 'failed' }}
      decisionSummary
    />,
  );
  for (const heading of headings) expect(html).toContain(heading);
  expect(html).toContain('AI 해석 실패');
  expect(html).toContain('정상이나 복구를 뜻하지 않습니다');
  expect(html).toContain('대응 지침이 저장되지 않았습니다');
  expect(html).toContain('원인 해석이 저장되지 않았습니다');
});

it('keeps the reset guide inside saved GPU recovery guidance without structured observations', () => {
  const result = fixture(books.find((b) => b.knowledge_key === 'RB-XID-79')!);
  delete obj(result.quality).triage_observations;
  const html = renderToStaticMarkup(<RcaNarrative result={result} decisionSummary />);
  for (const heading of headings) expect(html).toContain(heading);
  const response = html.slice(
    html.indexOf('id="rca-response-reference"'),
    html.indexOf('id="rca-observation-detail"'),
  );
  expect(response.match(/class="rca-reset-guide"/g)).toHaveLength(1);
  expect(response).toMatch(/복구[\s\S]*<details class="rca-reset-guide">[\s\S]*<\/details><\/li>/);
});
