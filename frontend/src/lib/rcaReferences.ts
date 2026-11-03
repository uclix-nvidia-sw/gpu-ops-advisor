import { num, obj, rows, str, type Row } from './live';

// Reviewed primary sources in the Runbook catalog. Collector/application source
// code remains available in processing details, not as operator remediation.
export function isOperatorReference(reference: Row): boolean {
  try {
    const url = new URL(str(reference.url));
    if (url.protocol !== 'https:' || url.username || url.password) return false;
    return (
      ['docs.nvidia.com', 'networking-docs.nvidia.com', 'docs.kernel.org'].includes(url.hostname) ||
      (url.hostname === 'github.com' && url.pathname.toLowerCase().startsWith('/nvidia/'))
    );
  } catch {
    return false;
  }
}

export function isOperatorGuidanceReference(reference: Row, sourceList: unknown): boolean {
  const indices = reference.source_indices;
  // Older saved guidance without source indices retains its explanatory text.
  if (!Array.isArray(indices) || !indices.length) return true;
  const sources = rows(sourceList);
  return indices.some(
    (index) => Number.isInteger(index) && isOperatorReference(obj(sources[num(index)])),
  );
}
