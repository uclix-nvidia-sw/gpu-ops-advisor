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

type Point = {
  text: string;
  details?: string[];
  toggle?: string;
  note?: string;
  counts?: [string, string][];
};

/** Compact only known generated related-error fields; retain all original evidence. */
function relatedPoints(items: string[]): Point[] {
  const output: Point[] = [];
  let other: Point | undefined;
  for (const text of items) {
    if (text.startsWith('같은 노드 다른 오류: ')) {
      if (!other) {
        other = {
          text: '',
          details: [],
          toggle: '오류 목록',
          note: '아래 오류는 이 보고서의 대상이 아닙니다. 별도 사건으로 확인하세요.',
        };
        output.push(other);
      }
      other.details!.push(
        text
          .replace(/^같은 노드 다른 오류: /, '')
          .replace(/, 이 보고서의 대상 아님\(별도 사건으로 확인\)$/, ''),
      );
      const codes = other.details!.map((s) => s.match(/^(S?XID:\d+)/)?.[1]);
      const quantity = codes.every(Boolean)
        ? `${new Set(codes).size}개 코드`
        : `${codes.length}개 항목`;
      other.text = `같은 노드 다른 오류: ${quantity} 관측.`;
      continue;
    }
    const excluded = text.startsWith('오류 로그 장치: ') ? text.indexOf(' (같은 노드의 ') : -1;
    if (excluded > 0 && text.endsWith('는 대조에서 제외)')) {
      output.push({
        text: text.slice(0, excluded),
        details: text
          .slice(excluded + ' (같은 노드의 '.length, -'는 대조에서 제외)'.length)
          .split(', '),
        toggle: '다른 오류 목록',
        note: '같은 노드에서 관측된 다른 오류입니다. 알림과 로그의 장치가 같은지 확인할 때는 제외했습니다.',
      });
      continue;
    }
    const history = text.match(/^(같은 호스트의 다른 오류(?:\(참고\))?): (.+)$/);
    if (history) {
      const parts = history[2].split(', ').map((p) => p.match(/^(.+) (\d+)건$/));
      if (parts.every((p) => p !== null)) {
        const counts = parts.map((p): [string, string] => [p![1], p![2]]);
        const families = [
          ...new Set(counts.map(([c]) => c.match(/^(S?XID):/)?.[1]).filter(Boolean)),
        ];
        output.push({
          text: `${history[1]}: ${families.length ? families.join('·') + ' 오류가' : '다른 오류가'} ${families.length > 1 ? '함께 ' : ''}관측됐습니다.`,
          counts,
          toggle: '코드별 건수',
        });
        continue;
      }
    }
    output.push({ text });
  }
  return output;
}

/** One numbered "1) 2)" line per item; a short "label: value" prefix is emphasised. */
export function RcaPoints({
  items,
  compactRelated = false,
}: {
  items: string[];
  compactRelated?: boolean;
}) {
  if (!items.length) return null;
  return (
    <ol className="rca-points">
      {(compactRelated ? relatedPoints(items) : items.map((text) => ({ text }) as Point)).map(
        ({ text, details, toggle, counts, note }, i) => {
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
              {(details || counts) && (
                <details className="rca-related-details">
                  <summary>
                    <span className="rca-when-closed">{toggle} 펼치기</span>
                    <span className="rca-when-open">{toggle} 접기</span>
                  </summary>
                  <div
                    className="rca-related-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label={`${toggle} 목록`}
                  >
                    {note && <p className="rca-related-note">{note}</p>}
                    {counts ? (
                      <table className="rca-related-counts">
                        <thead>
                          <tr>
                            <th>오류 코드</th>
                            <th>사건 수</th>
                          </tr>
                        </thead>
                        <tbody>
                          {counts.map(([code, count]) => (
                            <tr key={code}>
                              <td>{code}</td>
                              <td>{count}건</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <ul className="rca-related-list">
                        {details!.map((detail, index) => {
                          const parts = detail.split(' · ');
                          return (
                            <li key={index}>
                              <Ids text={parts.slice(0, 2).join(' · ')} />
                              {parts.length > 2 && (
                                <div>
                                  <Ids text={parts.slice(2).join(' · ')} />
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </details>
              )}
            </li>
          );
        },
      )}
    </ol>
  );
}

/** Step text with commands, prohibitions and disruptive actions set apart. */
export function Marked({ text }: { text: string }) {
  return (
    <>
      {highlightSegments(text).map((s, i) =>
        s.mark === 'command' ? (
          // Short commands stay on one line; long ones may wrap between words.
          <code className={`rca-mark-command${s.text.length <= 40 ? ' rca-nowrap' : ''}`} key={i}>
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
