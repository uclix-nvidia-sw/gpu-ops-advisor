// Response-step emphasis: commands to run, actions that disrupt work, and prohibitions.
// Rules stay narrow on purpose; common verbs ("확인합니다") are never emphasised.

export type Mark = 'command' | 'caution' | 'action';
export interface Segment {
  text: string;
  mark?: Mark;
}

// A command with its options, placeholders and paths; Korean particles end it.
const ARG = String.raw`(?:\s+(?:-{1,2}[\w.-]+(?:=[\w.,:/-]+)?|<[^<>]+>|[\w./:%=,*-]+))`;
const COMMANDS = [
  String.raw`(?:sudo\s+)?(?:kubectl|nvidia-smi|nvidia-bug-report\.sh|dmesg|journalctl|dcgmi|ipmitool|systemctl|findmnt|mdadm|lsmod|modprobe|mlxlink|ibstat|sminfo|lspci|ldconfig|nvsm|fsck|fleetint)\b${ARG}*`,
  String.raw`nvme\s+(?:list|smart-log|id-ctrl|error-log)\b${ARG}*`,
  String.raw`(?:sudo\s+)?(?:free|ps|ip|cat|grep)(?:\s+(?:-{1,2}[\w.-]+|\/[\w./*-]+))${ARG}*`,
  String.raw`(?:^|(?<=\s))--[\w-]+(?:\s+--[\w-]+)*`,
  String.raw`(?<![\w/])\/(?:proc|sys|var|etc|dev|run)\/[\w./*-]+`,
];
const DISRUPT = '재시작|재부팅|리셋|배출|교체';
// Prohibitions of an action, and loss of evidence or data; analysis caveats stay plain.
const CAUTION = [
  String.raw`(?:[가-힣]+[을를]\s)?(?:${DISRUPT}|조치|적용|운영|중단)하지\s?않(?:고|습니다|으며|아야)`,
  String.raw`(?:${DISRUPT}|조치)[을를]\s하지\s?않(?:고|습니다|으며|아야)`,
  String.raw`(?:${DISRUPT})(?:이나|은|는)?\s?(?:[가-힣]+\s)?필요하지 않습니다`,
  String.raw`사라지므로|사라지며|사라집니다|데이터가 손실|손실됐을|손상될`,
];
// Disruptive actions only when the sentence tells the operator to do them.
const ACTION = [
  String.raw`(?:(?:호스트|노드|GPU|모든 GPU·NVSwitch|작업)[을를]\s)?(?:${DISRUPT})(?:합니다|하거나|하고|한 뒤|하며)`,
  String.raw`작업 배출|전원 사이클`,
];
const PATTERN = new RegExp(
  `(${COMMANDS.join('|')})|(${CAUTION.join('|')})|(${ACTION.join('|')})`,
  'g',
);

export function highlightSegments(text: string): Segment[] {
  const out: Segment[] = [];
  let at = 0;
  for (const m of text.matchAll(PATTERN)) {
    const value = m[0].trimEnd();
    if (!value) continue;
    const start = m.index ?? 0;
    if (start > at) out.push({ text: text.slice(at, start) });
    out.push({ text: value, mark: m[1] ? 'command' : m[2] ? 'caution' : 'action' });
    at = start + value.length;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}
