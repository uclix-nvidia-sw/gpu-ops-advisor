import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaOperatorReport } from './RcaOperatorReport';
vi.mock('../lib/store', () => ({ useApp: () => ({ mode: 'classic' }) }));

it('links the six report sections even when observations are unavailable', () => {
  for (const decisionSummary of [false, true]) {
    const html = renderToStaticMarkup(
      <RcaOperatorReport result={{}} decisionSummary={decisionSummary} />,
    );
    const toc = html.match(/<nav class="rca-classic-toc"[^>]*>(.*?)<\/nav>/)?.[1] || '';
    const targets = [...toc.matchAll(/href="#([^"]+)"/g)].map((match) => match[1]);
    expect(targets).toHaveLength(6);
    for (const target of targets) expect(html).toContain(`id="${target}"`);
    expect(html.indexOf('rca-classic-toc')).toBeGreaterThan(html.indexOf('</header>'));
    expect(html).not.toContain('목업');
  }
});
