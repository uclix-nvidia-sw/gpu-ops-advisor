import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaNarrative } from './RcaNarrative';

describe('RCA report reading', () => {
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
