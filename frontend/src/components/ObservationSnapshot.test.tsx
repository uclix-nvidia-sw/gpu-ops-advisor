import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DataView, AlarmIdentity } from './live';
import { ObservationSnapshot } from './ObservationSnapshot';

describe('RCA evidence rendering', () => {
  it('stacks deeply nested fields without exposing hidden metadata by default', () => {
    const html = renderToStaticMarkup(
      <DataView
        value={{
          outer: {
            inner: { labels: { cluster: 'cpc2', customer: 'customer-b', checksum: 'privatehash' } },
          },
        }}
      />,
    );
    expect(html).toContain('data-stacked');
    expect(html).toContain('data-depth="3"');
    expect(html).toContain('customer-b');
    expect(html).not.toContain('privatehash');
  });
  it('renders Loki rows as a table with Korean time and raw disclosure', () => {
    const data = {
      data: [
        {
          timestamp: '1790837839405879050',
          labels: { test_id: 'fixture' },
          line: JSON.stringify({
            attributes: { health: 'Unhealthy', reason: 'XID 79 synthetic' },
            resources: { 'k8s.node.name': 'node-a' },
          }),
        },
      ],
    };
    const html = renderToStaticMarkup(
      <ObservationSnapshot value={data} fallback={<p>fallback</p>} />,
    );
    for (const word of ['<table', 'health', 'reason', 'node-a', 'KST', '테스트 알람', '원본 JSON'])
      expect(html).toContain(word);
    expect(html).not.toContain('fallback');
  });
  it('renders Mimir series and keeps empty or unknown snapshots explicit', () => {
    const html = renderToStaticMarkup(
      <ObservationSnapshot
        value={{ data: [{ metric: { UUID: 'GPU-test' }, values: [[1, '0']] }] }}
        fallback={null}
      />,
    );
    expect(html).toContain('시계열 라벨');
    expect(html).toContain('GPU-test');
    expect(
      renderToStaticMarkup(
        <ObservationSnapshot value={{ data: [] }} fallback={<p>기록 없음</p>} />,
      ),
    ).toContain('기록 없음');
  });
  it('uses display title, preserving the rule name as secondary text', () => {
    const html = renderToStaticMarkup(
      <AlarmIdentity
        record={{ target: { alertname: 'GPUAlert', title: 'XID synthetic', test_alarm: true } }}
      />,
    );
    expect(html).toContain('<strong>XID synthetic</strong>');
    expect(html).toContain('GPUAlert');
    expect(html).toContain('테스트 알람');
  });
});
