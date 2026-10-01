import labels from './rcaLabels.json';

export const rcaLabels = labels;
export const rcaReasons: Record<string, string> = labels.reasons;
export function missingGroups(codes: string[]) {
  return Object.entries(labels.groups)
    .map(([id, group]) => ({
      ...group,
      id,
      items: [...new Set(codes)].filter((code) => {
        const assigned =
          Object.entries(labels.groups).find(([, g]) =>
            (g.codes as string[]).includes(code),
          )?.[0] ?? 'quality';
        return assigned === id;
      }),
    }))
    .filter((group) => group.items.length);
}
export function purposeLabel(id: string) {
  const names: Record<string, string> = labels.purposes;
  const required: Record<string, string> = labels.required;
  return `${id} ${names[id] || '목적 미확인'} — ${required[id] || '필수 근거 미확인'}`;
}
