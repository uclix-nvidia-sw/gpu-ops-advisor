import { toneLabels, type Tone } from '../lib/rcaOperatorView';
import { highlightSegments } from '../lib/rcaHighlight';

export function ToneBadge({ tone, label }: { tone: Tone; label?: string }) {
  return <span className={`rca-badge tone-${tone}`}>{label || toneLabels[tone]}</span>;
}

const ID =
  /(GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|(?:PCI[: ])?[0-9a-f]{4,8}:[0-9a-f]{2}:[0-9a-f]{2}(?:\.[0-7])?)/gi;

/** Full GPU UUIDs and PCI addresses kept intact but set apart for reading. */
export function Ids({ text }: { text: string }) {
  return (
    <>
      {text.split(ID).map((part, i) =>
        i % 2 ? (
          <code className="rca-id" key={i}>
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
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
                <Ids text={body.slice(at)} />
              </>
            ) : (
              <Ids text={body} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Step text with commands, prohibitions and disruptive actions set apart. */
export function Marked({ text }: { text: string }) {
  return (
    <>
      {highlightSegments(text).map((s, i) =>
        s.mark === 'command' ? (
          <code className="rca-mark-command" key={i}>
            {s.text}
          </code>
        ) : s.mark ? (
          <mark className={`rca-mark-${s.mark}`} key={i}>
            {s.text}
          </mark>
        ) : (
          <Ids key={i} text={s.text} />
        ),
      )}
    </>
  );
}

/** Response-step sentences; the branch this alert reported moves first, marked with ▶. */
export function RcaStepPoints({ items, branches = [] }: { items: string[]; branches?: string[] }) {
  if (!items.length) return null;
  const hit = (text: string) => branches.some((b) => text.startsWith(`${b}:`));
  const ordered = [...items.filter(hit), ...items.filter((text) => !hit(text))];
  return (
    <ol className="rca-points">
      {ordered.map((text, i) => {
        const at = text.indexOf(': ');
        const labelled = at > 0 && at <= 32;
        return (
          <li key={i} className={hit(text) ? 'rca-branch-hit' : undefined}>
            {hit(text) && '▶ '}
            {labelled ? (
              <>
                <strong>{text.slice(0, at)}</strong>
                <Marked text={text.slice(at)} />
              </>
            ) : (
              <Marked text={text} />
            )}
          </li>
        );
      })}
    </ol>
  );
}
