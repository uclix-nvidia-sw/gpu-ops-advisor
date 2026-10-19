import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaNarrative } from './RcaNarrative';

describe('RCA report reading', () => {
  it('keeps frozen guidance conditions and avoids injecting generic causes', () => {
    const result = {
      quality: {
        report: { presentation: 'rca-material/1' },
        runbook_guidance: [
          {
            guidance: {
              schema: 'gpu-rca-guidance/1.0',
              cause_note: '추가된 일반 원인',
              next_checks: [],
              references: [],
            },
          },
        ],
      },
      narrative: [
        { id: 'cause', title: '분석 결과', text: 'Fleet disk 비정상 보고입니다.' },
        { id: 'action', title: '권고 대응', text: '유지보수 승인 후 점검합니다.' },
        { id: 'limits', title: '개발자 상세', text: 'producer_time_status missing_or_zero' },
      ],
    };
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaNarrative result={result} />);
    expect(html).toContain('유지보수 승인 후 점검합니다.');
    expect(html).not.toContain('일반적인 조사 방향:');
    expect(html).toContain('<summary>개발자 상세</summary>');
    expect(JSON.stringify(result)).toBe(before);
  });
  it('keeps the five operator sections visible and supporting material collapsed', () => {
    const result = {
      quality: { report: { presentation: 'incident-first/1' } },
      narrative: [
        { id: 'problem', title: '발생 내용', text: '사건 기록' },
        { id: 'impact', title: '영향과 심각도', text: '작업 영향 미확인' },
        { id: 'cause', title: '원인 분석', text: '원인 후보' },
        { id: 'action', title: '권고 조치', text: '조건부 복구 안내' },
        { id: 'next', title: '추가 확인 사항', text: '운영 모드 확인' },
        { id: 'guidance', title: '참고 지침·적용 조건', text: '문헌 원문' },
        { id: 'limits', title: '분석 한계', text: '조회 제한 원문' },
      ],
    };
    const before = JSON.stringify(result);
    const html = renderToStaticMarkup(<RcaNarrative result={result} consolidateChecks />);
    expect(html).toContain('운영 모드 확인');
    expect(html).toContain('<summary>참고 지침·적용 조건</summary>');
    expect(html).toContain('<summary>분석 한계</summary>');
    expect(html.match(/href="#rca-report-section-/g)).toHaveLength(5);
    expect(html.indexOf('영향과 심각도')).toBeLessThan(html.indexOf('원인 분석'));
    expect(JSON.stringify(result)).toBe(before);
  });
  it('shows findings-led reference guidance as a primary section without generic notes', () => {
    const html = renderToStaticMarkup(
      <RcaNarrative
        result={{
          quality: {
            report: { presentation: 'incident-first/2' },
            runbook_guidance: [
              {
                guidance: {
                  schema: 'gpu-rca-guidance/1.0',
                  cause_note: '일반 조사 방향 문장',
                  meaning: '일반 의미',
                  next_checks: [{ title: '일반 확인', text: '일반 확인 문장' }],
                  references: [],
                },
              },
            ],
          },
          narrative: [
            { id: 'problem', title: '발생 내용', text: '사건 기록' },
            { id: 'cause', title: '원인 분석', text: '판단: GPU 0 한 장치' },
            { id: 'guidance', title: '이 오류에 대한 참고 안내', text: 'Fleet 분류 Fatal' },
            { id: 'limits', title: '분석 한계', text: '발행 조사 지침 원문' },
          ],
        }}
      />,
    );
    expect(html).toContain('<h4 id="rca-report-title-2">이 오류에 대한 참고 안내</h4>');
    expect(html).toContain('<p>Fleet 분류 Fatal</p>');
    expect(html).not.toContain('<summary>이 오류에 대한 참고 안내</summary>');
    expect(html).not.toContain('일반 조사 방향 문장');
    expect(html).not.toContain('일반 확인 문장');
    expect(html).toContain('<summary>분석 한계</summary>');
    expect(html.match(/href="#rca-report-section-/g)).toHaveLength(3);
  });
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
    expect(html).toContain('다음에 확인할 내용');
    expect(html).toContain('이 오류에 대한 참고 안내');
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

it('separates a general XID cause from stored identity uncertainty without inventing recurrence', () => {
  const result = {
    runbook_revisions: [{ knowledge_key: 'RB-XID-79' }],
    device_observations: [{ pci_inventory_relation: 'not_in_reported_inventory' }],
    narrative: [
      { id: 'cause', title: '원인 판단', text: '장치 식별 불확실성이 원인일 가능성이 있다' },
      { id: 'guidance', text: 'Fleet 고정 카탈로그: GPU has fallen off the bus' },
    ],
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(html).toContain('장애 원인이 아니라 원인을 확정하지 못하는 이유');
  expect(html).toContain('<summary>저장된 원인 문장·해석 주의</summary>');
  expect(JSON.stringify(result)).toBe(before);
});

it('qualifies unmapped XID hardware candidates and preserves the original for inspection', () => {
  const result = {
    runbook_revisions: [{ knowledge_key: 'RB-XID-79' }],
    device_observations: [{ pci_inventory_relation: 'not_in_reported_inventory' }],
    narrative: [
      { id: 'problem', text: 'xid:79 보고는 확인했습니다.' },
      {
        id: 'cause',
        text: '보고된 PCI 주소 PCI:0000:01:00에 연결된 GPU가 전원 문제로 분리된 가능성',
      },
      { id: 'guidance', text: 'GPU has fallen off the bus' },
    ],
  };
  const before = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(html).toContain('XID 79 오류가 보고된 것을 확인했습니다.');
  expect(html).toContain('이번 기록은 오류 장치가 식별되지 않아 해당 원인을 뒷받침하지 못합니다.');
  expect(html.indexOf('저장된 원인 문장·해석 주의')).toBeLessThan(html.indexOf('연결된 GPU가'));
  expect(JSON.stringify(result)).toBe(before);
});
it('does not apply the XID interpretation to an unfamiliar error', () => {
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{
        narrative: [
          { id: 'problem', text: '새 오류 보고' },
          { id: 'cause', text: '원인 미확인' },
        ],
      }}
    />,
  );
  expect(html).not.toContain('전원 문제');
  expect(html).toContain('원인 미확인');
});

it('keeps failed objective visible while collapsing processing details', () => {
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{
        narrative: [{ id: 'problem', title: '발생 내용', text: 'SXID 이벤트 1건' }],
        quality: {
          rca_evaluation: { schema_version: '2', investigation: { stop_reason: 'goal_not_met' } },
        },
      }}
    />,
  );
  expect(html).toContain(
    '<summary>분석 처리: 목적 미달 · 가능한 보완 없음 · 수집·검토 상세</summary>',
  );
  expect(html).not.toContain('<details open');
  expect(html).toContain('SXID 이벤트 1건');
  expect(html).toContain('수집·증거 해석·분석 품질');
});

it('opens evaluation details for developers without changing report content', () => {
  const result = { narrative: [{ id: 'problem', title: '발생 내용', text: '관측 원문' }] };
  const developer = renderToStaticMarkup(<RcaNarrative result={result} evaluationExpanded />);
  const classic = renderToStaticMarkup(<RcaNarrative result={result} />);
  expect(developer).toContain('<details open="">');
  expect(classic).not.toContain('<details open');
  expect(developer).toContain('관측 원문');
  expect(classic).toContain('관측 원문');
});

it('does not present stale objective achievement as reviewed success in the summary', () => {
  const html = renderToStaticMarkup(
    <RcaNarrative
      result={{
        narrative: [{ id: 'problem', text: '관측 원문' }],
        quality: {
          rca_evaluation: {
            schema_version: '2',
            analysis_id: 'new',
            review: { execution_status: 'complete', analysis_id: 'old', verdict: 'acceptable' },
            investigation: {
              stop_reason: 'goal_achieved',
              objective: { status: 'achieved', analysis_id: 'old' },
            },
          },
        },
      }}
    />,
  );
  expect(html).toContain(
    '<summary>분석 처리: 종료 · 최종 분석 검토 기록 확인 · 수집·검토 상세</summary>',
  );
});
