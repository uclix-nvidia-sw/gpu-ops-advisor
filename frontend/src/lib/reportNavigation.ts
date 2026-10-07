import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { obj, str, type Row } from './live';

export const reportTabs = [
  { to: '/reports', label: '보고서 이력' },
  { to: '/schedules', label: '자동 보고서 설정' },
  { to: '/operator-guide', label: '운영자 가이드' },
];

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
