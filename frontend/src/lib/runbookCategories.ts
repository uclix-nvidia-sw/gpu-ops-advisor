import { obj, str, strings, type Row } from './live';

export const RUNBOOK_CATEGORIES = [
  'XID',
  'SXID',
  'OS',
  'Memory',
  'Disk',
  'Network',
  '기타',
] as const;
export type RunbookCategory = (typeof RUNBOOK_CATEGORIES)[number];

/** Use saved classification/search metadata, never words in remediation prose. */
export function runbookCategories(row: Row): RunbookCategory[] {
  if (row.kind !== 'runbook') return [];
  const content = obj(row.content),
    search = obj(content.search),
    classification = obj(content.classification);
  const codes = [str(content.code), ...strings(search.codes)];
  const events = strings(search.producer_events);
  const domain = str(classification.domain).toUpperCase(),
    category = str(classification.category).toLowerCase();
  const result: RunbookCategory[] = [];
  if (
    codes.some((c) => /^xid[:\s]\d+$/i.test(c)) ||
    events.includes('accelerator-nvidia-error-xid')
  )
    result.push('XID');
  if (
    codes.some((c) => /^sxid[:\s]\d+$/i.test(c)) ||
    events.includes('accelerator-nvidia-error-sxid')
  )
    result.push('SXID');
  if (category === 'os_resources' || events.includes('os')) result.push('OS');
  if (
    domain === 'GPU_MEMORY' ||
    /^(ecc_memory|memory_monitor|dcgm_memory_health)$/.test(category) ||
    events.includes('memory')
  )
    result.push('Memory');
  if (category === 'disk_filesystem' || events.includes('disk')) result.push('Disk');
  if (
    domain.startsWith('NETWORK') ||
    ['ethernet_link', 'infiniband_port', 'nccl_communication', 'gpudirect_rdma'].includes(
      category,
    ) ||
    events.includes('network-ethernet')
  )
    result.push('Network');
  return result.length ? result : ['기타'];
}
