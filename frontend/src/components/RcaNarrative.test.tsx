import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaNarrative } from './RcaNarrative';

describe('RCA report reading', () => {
  it('preserves published guidance separately from findings when checks are consolidated', () => {
    const html = renderToStaticMarkup(
      <RcaNarrative
        consolidateChecks
        result={{
          narrative: [
            { id: 'problem', title: '감지된 문제', text: '오류 보고 확인' },
            {
              id: 'guidance',
              title: 'Runbook 조사 지침·적용 조건',
              text: '문헌 적용 조건: R565\n\n조건부 권고: 유지보수 승인 후 검토',
            },
          ],
        }}
      />,
    );
    expect(html).toContain('Runbook 조사 지침·적용 조건');
    expect(html).toContain('유지보수 승인 후 검토');
    expect(html).toContain('문헌 적용 조건: R565');
  });
  it('moves repeated checks out of the primary report and explains opaque identifiers', () => {
    const result = {
      narrative: [
        {
          id: 'problem',
          title: '감지된 문제',
          text: '보고된 오류 코드: xid:79.\n\n대상 클러스터: sample 노드: node-a\n\n대상 식별 정보\n장비: opaque-id',
        },
        { id: 'next', title: '추가 확인', text: '중복 확인 문장' },
        { id: 'limits', title: '분석 한계', text: '중복 한계 문장' },
      ],
    };
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaNarrative result={result} consolidateChecks />);
    expect(html).toContain('노드: node-a');
    expect(html).toContain('<summary>대상 연결용 식별자</summary>');
    expect(html).toContain('고장 장치의 확정 정보가 아닙니다');
    expect(html).not.toContain('중복 확인 문장');
    expect(html).not.toContain('중복 한계 문장');
    expect(JSON.stringify(result)).toBe(before);
  });
  it('keeps every stored limitation and next check in distinct readable items', () => {
    const result = {
      narrative_status: 'failed',
      narrative: [
        { id: 'next', title: '추가 확인', text: '대상 확인\n\n시각 확인' },
        {
          id: 'limits',
          title: '분석 한계',
          text: '원인 미확정\n\nXID 79 <script>test</script>\n\n미수행',
        },
      ],
    };
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaNarrative result={result} />);
    expect(html.match(/<li>/g)).toHaveLength(5);
    expect(html).toContain('<li>원인 미확정</li>');
    expect(html).toContain('XID 79 &lt;script&gt;test&lt;/script&gt;');
    expect(html).toContain('기본 보고서');
    expect(html).not.toContain('<script>');
    expect(html).toContain('href="#rca-report-section-1"');
    expect(html).toContain('분석 한계 1개 더 보기');
    expect(html).not.toContain('<details open');
    expect(html.indexOf('원인 미확정')).toBeLessThan(html.indexOf('분석 한계 1개 더 보기'));
    expect(JSON.stringify(result)).toBe(before);
  });
  it('keeps unfamiliar sections and missing text without inventing a conclusion', () => {
    const html = renderToStaticMarkup(
      <RcaNarrative
        result={{
          narrative: [
            { id: 'other', title: '새 항목', text: '미확인. v1.2 / 0000:01:00\n같은 원문' },
            { id: 'empty', title: '빈 항목' },
          ],
        }}
      />,
    );
    expect(html).toContain('미확인. v1.2 / 0000:01:00\n같은 원문');
    expect(html).toContain('저장된 설명이 없습니다');
    expect(html).not.toContain('<li>');
  });
  it('does not make a final report when no narrative was stored', () => {
    expect(renderToStaticMarkup(<RcaNarrative result={{}} />)).toBe('');
  });
});

it('renders only the incident timestamp in Korea time without rewriting saved text', () => {
  const result = {
    narrative: [
      {
        id: 'problem',
        title: '감지된 문제',
        text: '사건 기준 시각: 2026-10-12T09:01:10Z\n실제 오류 발생 시각과 같다고 단정할 수 없습니다.',
      },
    ],
  };
  const original = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(html).toContain('18:01:10');
  expect(html).toContain('KST (한국 시각)');
  expect(html).toContain('실제 오류 발생 시각과 같다고 단정할 수 없습니다.');
  expect(JSON.stringify(result)).toBe(original);
});
