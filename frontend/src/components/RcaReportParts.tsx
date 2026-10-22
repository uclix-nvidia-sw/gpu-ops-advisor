import { toneLabels, type Tone } from '../lib/rcaOperatorView';

export function ToneBadge({ tone, label }: { tone: Tone; label?: string }) {
  return <span className={`rca-badge tone-${tone}`}>{label || toneLabels[tone]}</span>;
}

/** One numbered "1) 2)" line per item; a short "label: value" prefix is emphasised. */
export function RcaPoints({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ol className="rca-points">
      {items.map((text, i) => {
        const estimate = text.startsWith('(추정) ');
        const body = estimate ? text.slice(5) : text;
        const at = body.indexOf(': ');
        return (
          <li key={i}>
            {estimate && <span className="rca-estimate">추정</span>}
            {at > 0 && at <= 24 ? (
              <>
                <strong>{body.slice(0, at)}</strong>
                {body.slice(at)}
              </>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}
