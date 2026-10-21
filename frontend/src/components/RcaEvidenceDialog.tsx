import { obj, str, useResource } from '../lib/live';
import { formatDate } from '../lib/domain';
import { Modal } from './ui';
import { QueryState } from './live';
import { ObservationSnapshot, RawJson } from './ObservationSnapshot';

export function RcaEvidenceDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useResource(`/evidence/${encodeURIComponent(id)}`);
  const evidence = obj(q.data);
  return (
    <Modal title="RCA 관측 원문" wide onClose={onClose}>
      <QueryState query={q}>
        <p>
          {str(evidence.query_id)} · {str(evidence.cluster_id)} ·{' '}
          {formatDate(str(evidence.time_start))} ~ {formatDate(str(evidence.time_end))} KST
        </p>
        <ObservationSnapshot
          value={evidence.snapshot}
          fallback={<pre>{JSON.stringify(evidence.snapshot, null, 2)}</pre>}
        />
        <details>
          <summary>수집 메타데이터·전체 응답</summary>
          <RawJson value={evidence} />
        </details>
      </QueryState>
    </Modal>
  );
}
