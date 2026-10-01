import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { obj, str, type Row } from './live';

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
    const frame = requestAnimationFrame(() =>
      document.getElementById(`report-row-${row}`)?.scrollIntoView({ block: 'center' }),
    );
    return () => cancelAnimationFrame(frame);
  }, [location.key, row, loaded]);
  return location.pathname + location.search;
}
