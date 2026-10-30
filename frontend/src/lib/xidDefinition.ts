import labels from './incidentLabels.json';

export interface XidDefinition {
  name: string;
  meaning: string;
  source: string;
}

// Presentation-only catalog annotation. Never mutate saved evidence or results.
export function xidDefinition(code: string): XidDefinition | undefined {
  return (labels as Record<string, { official?: XidDefinition }>)[code.toLowerCase()]?.official;
}
