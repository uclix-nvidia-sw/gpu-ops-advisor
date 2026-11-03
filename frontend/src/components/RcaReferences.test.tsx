import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaOperatorReport } from './RcaOperatorReport';
import { isOperatorReference } from '../lib/rcaReferences';

const root = fileURLToPath(new URL('../../../rcca-agent/runbooks', import.meta.url));
const books = readdirSync(root, { recursive: true })
  .filter((name) => /(?:^|[/\\])RB-.*\.json$/.test(String(name)))
  .map((name) => JSON.parse(readFileSync(join(root, String(name)), 'utf8')));

it('uses the pinned Runbook meaning without a catalog override or sentence truncation', () => {
  const meaning =
    '과거 문헌의 코드 의미입니다. 현재 적용 제품의 범위입니다. 이 세 번째 문장은 적용 예외를 설명합니다.';
  const result = {
    result_status: 'partial',
    missing_inputs: ['model_analysis_failed'],
    quality: {
      triage_observations: {
        schema: 'rca-triage-observations/1',
        target: { node: 'dgx01', title: 'XID 9 PCI:0000:07:00' },
        logs: [{ code: 'xid:9', device: '0000:07:00', reports: 1 }],
      },
      runbook_guidance: [{ guidance: { meaning, next_checks: [], references: [] } }],
    },
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} />);
  const glance = html.slice(
    html.indexOf('class="rca-glance"'),
    html.indexOf('id="rca-response-reference"'),
  );
  expect(glance).toContain(meaning);
  expect(glance).not.toContain('현재 표의 A100');
  expect(JSON.stringify(result)).toBe(before);
});

it('preserves all 284 Runbook references while separating implementation from operator material', () => {
  expect(books).toHaveLength(284);
  for (const book of books) {
    const result = {
      result_status: 'partial',
      quality: {
        runbook_guidance: [
          { guidance: book.content.operator_guidance, sources: book.content.sources },
        ],
      },
    };
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaOperatorReport result={result} />);
    const references = html.slice(html.indexOf('id="rca-references"'));
    const split = references.indexOf('<summary>수집 원문·처리 상세</summary>');
    expect(split, book.knowledge_key).toBeGreaterThan(0);
    const visible = references.slice(0, split);
    const detail = references.slice(split);
    for (const source of book.content.sources) {
      const expected = isOperatorReference(source) ? visible : detail;
      expect(expected, `${book.knowledge_key}: ${source.url}`).toContain(source.url);
      if (!isOperatorReference(source)) expect(visible).not.toContain(source.url);
    }
    expect(JSON.stringify(result)).toBe(before);
    for (const heading of [
      '1. 한눈에 보기',
      '2. 대응 순서',
      '3. 관련 로그·메트릭',
      '4. 분석 및 해석',
      '5. 이전 사건 이력',
      '6. 참고 자료',
    ]) {
      expect(html, book.knowledge_key).toContain(heading);
    }
  }
});

it('moves internal-only reference explanations and retains unclassified legacy explanations', () => {
  const result = {
    quality: {
      runbook_guidance: [
        {
          sources: [
            {
              url: 'https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html',
              section: '공식 정의',
            },
            {
              url: 'https://github.com/uclix-nvidia-sw/gpu-ops-advisor/blob/revision/agents/config.example.json',
              section: '구현 설정',
            },
          ],
          guidance: {
            references: [
              { title: '공식 대응', text: '문서의 적용 조건입니다.', source_indices: [0] },
              { title: '개발용 계약', text: '내부 수집 연결 정보입니다.', source_indices: [1] },
              { title: '이전 안내', text: '과거 저장본의 안내입니다.' },
            ],
          },
        },
      ],
    },
  };
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} />);
  const split = html.indexOf('<summary>수집 원문·처리 상세</summary>');
  expect(html.slice(0, split)).toContain('문서의 적용 조건입니다.');
  expect(html.slice(0, split)).toContain('과거 저장본의 안내입니다.');
  expect(html.slice(0, split)).not.toContain('내부 수집 연결 정보입니다.');
  expect(html.slice(split)).toContain('내부 수집 연결 정보입니다.');
});

it('keeps official NVIDIA code definitions and Linux documentation, without trusting lookalike hosts', () => {
  for (const url of [
    'https://github.com/NVIDIA/DCGM/blob/revision/dcgmlib/dcgm_errors.h',
    'https://docs.kernel.org/admin-guide/ras.html',
  ])
    expect(isOperatorReference({ url })).toBe(true);
  for (const url of [
    'https://docs.nvidia.com.evil.test/page',
    'https://github.com/NVIDIA-lookalike/file',
    'https://github.com/gpud-dev/gpud',
    'http://docs.nvidia.com/page',
    'invalid',
  ])
    expect(isOperatorReference({ url })).toBe(false);
});
