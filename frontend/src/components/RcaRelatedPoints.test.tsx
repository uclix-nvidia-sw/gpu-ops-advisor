import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaPoints, Marked } from './RcaReportParts';

it('groups other errors only, retaining every note and the visible core facts', () => {
  const notes = Array.from(
    { length: 27 },
    (_, i) => `같은 노드 다른 오류: XID:${i + 1} · GPU 1 · 원문 ${i}`,
  );
  const items = ['대상: GPU 3', ...notes, '누구에게 영향: 파드 A', '우선 대응: 원문 보존'];
  const html = renderToStaticMarkup(<RcaPoints items={items} compactRelated />);
  expect(html.match(/<details/g)).toHaveLength(1);
  expect(html).toContain('27개 코드 관측');
  for (const note of notes) {
    for (const part of note.replace('같은 노드 다른 오류: ', '').split(' · ')) {
      expect(html).toContain(part);
    }
  }
  expect(html.indexOf('누구에게 영향')).toBeGreaterThan(html.indexOf('</details>'));
  expect(html).not.toContain('<details open');
  expect(html.match(/같은 노드 다른 오류/g)).toHaveLength(1);
  expect(items).toHaveLength(30);
});

it('keeps identity visible and history counts inside bounded disclosures', () => {
  const html = renderToStaticMarkup(
    <RcaPoints
      compactRelated
      items={[
        '오류 로그 장치: PCI:0000:4e:00 → 알림과 일치 (같은 노드의 GPU 1 XID:2, GPU 2 XID:3는 대조에서 제외)',
        '같은 호스트의 다른 오류: XID:48 4건, SXID:11001 16건',
        '(추정) 동시 발생만으로 원인 관계를 확정하지 않습니다.',
      ]}
    />,
  );
  expect(html.indexOf('알림과 일치')).toBeLessThan(html.indexOf('<details'));
  expect(html).toContain('다른 오류 목록 펼치기');
  expect(html).toContain('<li>GPU 1 XID:2</li><li>GPU 2 XID:3</li>');
  expect(html).not.toContain('대조에서 제외한 다른 오류');
  expect(html).toContain('<td>SXID:11001</td><td>16건</td>');
  expect(html).toContain('동시 발생만으로 원인 관계를 확정하지 않습니다.');
  expect(
    renderToStaticMarkup(
      <RcaPoints compactRelated items={['같은 호스트의 다른 오류: 형식 미확인 원문']} />,
    ),
  ).not.toContain('<details');
  expect(renderToStaticMarkup(<Marked text="nvidia-smi" />)).toContain('rca-mark-command');
});
