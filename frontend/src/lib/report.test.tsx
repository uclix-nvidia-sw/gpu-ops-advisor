import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReportContent } from '../components/ReportContent';
import { reportObservations } from './report';

describe('report presentation', () => {
  it('shows usable observations, unknown allocation and escaped targets separately', () => {
    const html = renderToStaticMarkup(
      <ReportContent
        onEvidence={() => {}}
        value={{
          result_status: 'partial',
          narrative_status: 'omitted',
          evidence_refs: ['e1'],
          topics: [
            {
              topic_id: 'O02',
              status: 'partial',
              missing_inputs: ['allocation_contract_missing'],
              metrics: [
                {
                  id: 'O02.mapped_gpu_hours',
                  value: 7.9864,
                  unit: 'GPU-hours',
                  target: { namespace: '<script>bad</script>' },
                },
                {
                  id: 'O02.allocated_gpu_hours',
                  value: null,
                  quality: { reason: 'required_data_missing' },
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('GPU–Pod 연결 관측 시간');
    expect(html).toContain('7.986');
    expect(html).toContain('산출 불가');
    expect(html).toContain('정확한 할당량을 확정할 수 없습니다');
    expect(html).not.toContain('<script>');
    expect(html).toContain('<details><summary>원본 결과 보기');
  });
  it('merges query chunks once even when multiple topics reuse the same evidence', () => {
    const quality = {
      observations: [
        { query_id: 'D06', cluster_id: 'cpc-1', tool_status: 'ok', sample_count: 4000 },
        {
          query_id: 'D06',
          cluster_id: 'cpc-1',
          tool_status: 'partial',
          sample_count: 3000,
          reason: 'source_warning',
        },
        { query_id: 'D08', cluster_id: 'cpc-1', tool_status: 'empty', sample_count: 0 },
      ],
    };
    const summary = reportObservations({ topics: [{ quality }, { quality }] });
    expect(summary).toHaveLength(2);
    expect(summary[0]).toMatchObject({
      sample_count: 7000,
      statuses: ['ok', 'partial'],
      reasons: ['source_warning'],
    });
    expect(summary[1]).toMatchObject({ sample_count: 0, statuses: ['empty'] });
  });
});
