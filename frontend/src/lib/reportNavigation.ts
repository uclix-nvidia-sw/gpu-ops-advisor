import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { obj, str, type Row } from './live';

export const reportTabs = [
  { to: '/reports', label: '보고서 이력' },
  { to: '/schedules', label: '자동 보고서 설정' },
  { to: '/operator-guide', label: '운영자 가이드' },
];

export function numberReportSections(sections: string[][]) {
  const numbers = new Map<string, string>();
  const counts = new Map<string, number>();
  return sections.map(([id, label, parentId]) => {
    if (id === 'new-review-records') return [id, label, '', ''];
    const parent = parentId && numbers.has(parentId) ? parentId : '';
    const count = (counts.get(parent) || 0) + 1;
    counts.set(parent, count);
    const number = parent ? `${numbers.get(parent)}.${count}` : String(count);
    numbers.set(id, number);
    return [id, label, parent ? number : number.padStart(2, '0'), parent];
  });
}

export function reportReturnPath(state: unknown) {
  const path = str(obj(state).reportList);
  return /^\/reports(?:\?[^#]*)?$/.test(path) ? path : '/reports';
}

export function useReportListPosition(items: Row[]) {
  const location = useLocation();
  const row = str(obj(location.state).reportRow);
  const loaded = items.some((item) => item.id === row);
  useEffect(() => {
    if (!loaded) return;
    const frame = requestAnimationFrame(() => {
      const card = document.getElementById(`report-row-${row}`);
      card?.scrollIntoView({ block: 'start' });
      const link = card?.matches('a')
        ? card
        : card?.querySelector<HTMLElement>('a.report-history-title');
      link?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [location.key, row, loaded]);
  return location.pathname + location.search;
}
