import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { incidentName, incidentView } from './incidentOverview';
import { operatorView } from './rcaOperatorView';
import { xidDefinition } from './xidDefinition';
import { RcaOperatorReport } from '../components/RcaOperatorReport';
import labels from './incidentLabels.json';

it('shows the official driver source for XID 173 while retaining the stored explanation', () => {
  const result = {
    quality: {
      triage_observations: {
        schema: 'rca-triage-observations/1',
        target: { title: 'XID 173 C2C Fatal Link Failure', node: 'example' },
        logs: [],
      },
      runbook_guidance: [{ guidance: { meaning: '기존 수집기 설명 원문' } }],
    },
  };
  const saved = JSON.stringify(result);
  const html = renderToStaticMarkup(<RcaOperatorReport result={result} />);
  expect(html).toContain('NVIDIA 공식 드라이버');
  expect(html).toContain('/NVIDIA/open-gpu-kernel-modules/blob/ca2d03e6');
  expect(html).toContain('기존 수집기 설명 원문');
  expect(JSON.stringify(result)).toBe(saved);
});

const codes = [87, 90, 91, 108, 126, 127, 128, 129, 130, 131, 132, 134, 135, 136, 138, 139, 141];

it.each(codes)(
  'annotates Reserved XID %s in lists and stored reports without changing evidence',
  (code) => {
    const raw = `XID ${code} RESERVED_XID Reserved detected on GPU PCI:0000:07:00`;
    const view = incidentView({ target: { title: raw }, occurred_at: '2026-10-30T05:00:00Z' });
    const definition = xidDefinition(`xid:${code}`)!;
    expect(incidentName(view)).toBe(definition.name);
    expect(view.raw).toBe(raw);
    expect(definition.meaning).not.toContain('Reserved');
    const result = {
      quality: {
        triage_observations: {
          schema: 'rca-triage-observations/1',
          target: { title: raw, node: 'dgx02' },
          logs: [{ code: `xid:${code}`, device: '0000:07:00', message: raw, reports: 1 }],
        },
        runbook_guidance: [{ guidance: { meaning: 'Fleet·GPUd 고정 정의는 Reserved입니다.' } }],
      },
    };
    const saved = JSON.stringify(result);
    expect(operatorView(result)?.meaning).toBe(definition.meaning);
    const html = renderToStaticMarkup(<RcaOperatorReport result={result} />);
    expect(html).toContain(definition.meaning);
    expect(html).toContain('저장 당시 오류 설명 원문');
    expect(html).toContain('Fleet·GPUd 고정 정의는 Reserved입니다.');
    expect(html).toContain(raw);
    expect(html).toContain(definition.source);
    expect(JSON.stringify(result)).toBe(saved);
  },
);

it('leaves unknown, SXID and received descriptive names intact', () => {
  for (const [raw, name] of [
    ['XID 999 Reserved', 'Reserved'],
    ['SXID 128 Reserved', 'Reserved'],
    ['XID 128 specific driver description', 'specific driver description'],
  ]) {
    expect(incidentName(incidentView({ target: { title: raw } }))).toBe(name);
  }
  expect(xidDefinition('xid:128')?.meaning).toContain('A100·H100은 적용 대상이 아닙니다');
  expect(xidDefinition('xid:91')?.meaning).toContain('미사용(Unused)');
});

it.each(
  Object.keys(labels).filter((code) => xidDefinition(code)?.meaning.includes('미사용(Unused)')),
)('displays the reviewed Unused definition for %s and preserves the original', (code) => {
  const raw = `XID ${code.split(':')[1]} ORIGINAL_MNEMONIC Unused detected on GPU PCI:0000:07:00`;
  const v = incidentView({ target: { title: raw } });
  expect(incidentName(v)).toBe(xidDefinition(code)?.name);
  expect(v.raw).toBe(raw);
});

it.each(['0 (err status 0x00000000)', '33 (err status 0x00000002)'])(
  'separates NVLink diagnostic fields %s from the name without losing them',
  (suffix) => {
    const raw = `[Warning] accelerator-nvidia-error-xid: XID 146.${suffix} NVLINK_TLW_ERROR NVLINK: TLW Error detected on GPU PCI:0000:0f:00 UUID:GPU-example`;
    const v = incidentView({ target: { title: raw } });
    expect(incidentName(v)).toBe('NVLink TLW 오류');
    expect(v.codeText).toBe('XID 146');
    expect(v.device).toBe('0000:0f:00');
    expect(v.uuid).toBe('GPU-example');
    expect(v.raw).toBe(raw);
  },
);

it('does not turn a diagnostic status into a healthy verdict or strip unknown prose', () => {
  const raw = 'XID 146.0 (err status unavailable) NVLINK_TLW_ERROR';
  expect(incidentName(incidentView({ target: { title: raw } }))).toContain(
    '(err status unavailable)',
  );
});

it.each([39, 40, 41])(
  'explains collector Unused XID %s as the official copy-engine exception',
  (code) => {
    const raw = `XID ${code} ROBUST_CHANNEL_CE${code - 39}_ERROR Unused detected on GPU`;
    expect(incidentName(incidentView({ target: { title: raw } }))).toBe(
      `GPU 데이터 복사 엔진 CE${code - 39} 예외`,
    );
  },
);
