import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { useState } from 'react';

const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
const pad = (n: number) => String(n).padStart(2, '0');

/** Day keys of a "YYYY-MM" month, Sunday first, with blanks before the 1st. */
export function monthCells(month: string): string[] {
  const [y, m] = month.split('-').map(Number);
  const blanks = new Date(Date.UTC(y, m - 1, 1)).getUTCDay();
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [
    ...Array<string>(blanks).fill(''),
    ...Array.from({ length: days }, (_, i) => `${month}-${pad(i + 1)}`),
  ];
}

export function shiftMonth(month: string, by: number) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}

/** First click starts a range, the second ends it; the same day twice is that single day. */
export function pickDay(
  anchor: string,
  day: string,
): { anchor: string } | { first: string; last: string } {
  if (!anchor) return { anchor: day };
  return { first: anchor < day ? anchor : day, last: anchor < day ? day : anchor };
}

/** Range picker for inclusive KST days; future days are not selectable. */
export function RangeCalendar({
  first,
  last,
  today,
  label,
  onChange,
}: {
  first: string;
  last: string;
  today: string;
  label: string;
  onChange: (first: string, last: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [month, setMonth] = useState(last.slice(0, 7)),
    [anchor, setAnchor] = useState('');
  const close = () => {
    setOpen(false);
    setAnchor('');
  };
  const lo = anchor || first,
    hi = anchor || last;
  return (
    <div className="oh-cal-wrap">
      <button
        type="button"
        className="oh-cal-btn"
        aria-expanded={open}
        aria-controls="oh-cal"
        onClick={() => {
          if (open) return close();
          setMonth((last || today).slice(0, 7));
          setOpen(true);
        }}
      >
        <CalendarDays size={15} aria-hidden="true" />
        {label}
      </button>
      {open && (
        <div
          id="oh-cal"
          className="oh-cal"
          role="dialog"
          aria-label="조회 기간 달력"
          onKeyDown={(e) => e.key === 'Escape' && close()}
        >
          <div className="oh-cal-head">
            <button
              type="button"
              aria-label="이전 달"
              onClick={() => setMonth(shiftMonth(month, -1))}
            >
              <ChevronLeft size={16} />
            </button>
            <b>
              {month.slice(0, 4)}년 {Number(month.slice(5))}월
            </b>
            <button
              type="button"
              aria-label="다음 달"
              disabled={month >= today.slice(0, 7)}
              onClick={() => setMonth(shiftMonth(month, 1))}
            >
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="oh-cal-grid">
            {WEEK.map((w) => (
              <span key={w} className="w">
                {w}
              </span>
            ))}
            {monthCells(month).map((day, i) =>
              day ? (
                <button
                  key={day}
                  type="button"
                  disabled={day > today}
                  aria-label={day}
                  aria-pressed={day >= lo && day <= hi}
                  className={day === lo || day === hi ? 'edge' : day > lo && day < hi ? 'in' : ''}
                  onClick={() => {
                    const next = pickDay(anchor, day);
                    if ('anchor' in next) return setAnchor(next.anchor);
                    onChange(next.first, next.last);
                    close();
                  }}
                >
                  {Number(day.slice(8))}
                </button>
              ) : (
                <span key={`blank-${i}`} />
              ),
            )}
          </div>
          <p>
            {anchor
              ? `${anchor} 선택됨 · 다른 끝 날짜를 고르세요. 같은 날을 다시 누르면 하루만 봅니다.`
              : '시작일 → 종료일 순서로 고르세요. 같은 날을 두 번 누르면 하루만 봅니다.'}
          </p>
        </div>
      )}
    </div>
  );
}
