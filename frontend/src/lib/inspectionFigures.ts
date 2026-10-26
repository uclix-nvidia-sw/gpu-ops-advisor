// Inspection-area figures from docs/rca-animations (S = SXM example, P = PCIe example).
// A figure is shown only under a Runbook step whose text directs physical work on that
// area; matching the error code alone never inserts one. Mapped step titles are checked
// against the repository Runbooks by inspectionFigures.test.ts.
export type FigureId = 'S1' | 'P1' | 'S2' | 'S3' | 'P3';

export const FIGURES: Record<FigureId, { title: string; caption: string }> = {
  S1: { title: 'SXM(예시) · GPU', caption: '8U · GPU 8개 장착 영역' },
  P1: { title: 'PCIe(예시) · GPU', caption: '4U · 후단 GPU 8개 영역' },
  S2: { title: 'SXM(예시) · NVSwitch', caption: '8U · NVSwitch 영역 전체' },
  S3: { title: 'SXM(예시) · 네트워크 포트', caption: '데이터 포트 영역 전체 · BMC 제외' },
  P3: { title: 'PCIe(예시) · 네트워크 포트', caption: '데이터 포트 영역 전체 · BMC 제외' },
};

const GPU: FigureId[] = ['S1', 'P1'];
const PORTS: FigureId[] = ['S3', 'P3'];

// Alert code (xid:N / sxid:N) or Fleet component → Runbook step title → figures.
// ponytail: exact titles; a renamed step drops its figure until this table follows.
export const INSPECTION_STEPS: Record<string, Record<string, FigureId[]>> = {
  // GPU reseat when the GPU stays missing after the host restart.
  'xid:79': { '복구: 호스트 재시작 (RESTART_BM)': GPU },
  // CHECK_MECHANICALS: seating and auxiliary power connectors.
  'xid:54': { '복구 조치': GPU },
  // GPU-side NVLink mechanical connection check and reseat.
  'xid:74': { '오류별 판단 기준': GPU },
  // NVSwitch hardware inspection request; SXID uses the SXM example only.
  'sxid:11001': { '공급사 전달 (재발)': ['S2'] },
  'accelerator-nvidia-dcgm-pcie': { 복구: GPU },
  'accelerator-nvidia-infiniband': { 복구: PORTS },
  'network-ethernet': { 복구: PORTS },
};

/** Figures per step title present in this report (each figure is mapped to one step). */
export function inspectionFigures(key: string, stepTitles: string[]) {
  const table = INSPECTION_STEPS[key.toLowerCase()] || {};
  return new Map(stepTitles.filter((t) => table[t]).map((t) => [t, table[t]]));
}

export const figureUrl = (id: FigureId, kind: 'png' | 'webp') =>
  `${import.meta.env.BASE_URL}inspection-figures/${id}.${kind}`;
