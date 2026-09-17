import { useState } from 'react';
import { Badge, Field, Modal, NavTabs, PageHead, Panel } from '../components/ui';
import { DataView, More, QueryState } from '../components/live';
import { obj, queryPath, str, useList, useResource, type Row } from '../lib/live';
import { formatDate } from '../lib/domain';
import { useApp } from '../lib/store';
export function assetTarget(row: Row): Row {
  const kind = str(row.subject_kind),
    a = obj(row.attributes);
  return {
    kind,
    cluster_id: row.cluster_id,
    ...(kind === 'pod'
      ? { pod_uid: row.subject_key, namespace: a.namespace }
      : kind === 'gpu'
        ? { gpu_uuid: row.subject_key }
        : { node_uid: row.subject_key }),
  };
}
export function Fleet({ view }: { view: string }) {
  const app = useApp();
  const [chosen, setChosen] = useState(''),
    [chosenNamespace, setNamespace] = useState(''),
    [kind, setKind] = useState(view === 'workloads' ? 'pod' : 'node'),
    [selected, setSelected] = useState<Row | null>(null);
  const cluster = app.scope.clusters.find((c) => c.cluster_id === chosen) || app.scope.clusters[0];
  const namespace = cluster?.namespaces
    ? cluster.namespaces.includes(chosenNamespace)
      ? chosenNamespace
      : cluster.namespaces[0]
    : chosenNamespace;
  const assets = useList(
    app.ready && cluster && view !== 'quality'
      ? queryPath('/assets', {
          cluster: cluster.cluster_id,
          kind,
          limit: 50,
          ...(kind === 'pod' && namespace ? { namespace } : {}),
        })
      : null,
  );
  const query = useResource(app.ready && view === 'quality' ? '/observations/query' : null, {
    scope: app.scope,
    time_range: app.timeRange,
    timezone: 'Asia/Seoul',
    query_id: 'collection_quality',
  });
  const items = assets.items.filter(
    (a) =>
      !cluster?.namespaces ||
      kind !== 'pod' ||
      cluster.namespaces.includes(str(obj(a.attributes).namespace)),
  );
  return (
    <div className="page">
      <PageHead
        eyebrow="FLEET & OBSERVABILITY"
        title="자산·관측"
        description="수집된 식별 이력과 저장된 관측을 조회합니다."
      />
      <NavTabs
        items={[
          { to: '/fleet/assets', label: '장비·GPU' },
          { to: '/fleet/workloads', label: 'Pod·워크로드' },
          { to: '/fleet/quality', label: '관측 품질' },
        ]}
      />
      {view === 'quality' ? (
        <Panel title="관측 품질">
          <QueryState query={query}>
            <div className="live-padding">
              <Badge status={str(query.data?.tool_status, 'unknown')} />
              <DataView value={query.data} />
            </div>
          </QueryState>
        </Panel>
      ) : (
        <Panel
          title={view === 'workloads' ? '워크로드 목록' : '자산 목록'}
          description="수집되지 않은 자산은 목록에 표시되지 않습니다."
        >
          <div className="live-toolbar">
            <Field label="CPC">
              <select value={cluster?.cluster_id || ''} onChange={(e) => setChosen(e.target.value)}>
                {app.scope.clusters.map((c) => (
                  <option key={c.cluster_id}>{c.cluster_id}</option>
                ))}
              </select>
            </Field>
            {view === 'workloads' &&
              (cluster?.namespaces ? (
                <Field label="Namespace">
                  <select value={namespace} onChange={(e) => setNamespace(e.target.value)}>
                    {cluster.namespaces.map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </Field>
              ) : (
                <Field label="Namespace" hint="비우면 전체 Namespace를 조회합니다.">
                  <input value={chosenNamespace} onChange={(e) => setNamespace(e.target.value)} />
                </Field>
              ))}
            {view !== 'workloads' && (
              <Field label="자산 종류">
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="node">Node</option>
                  <option value="gpu">GPU</option>
                </select>
              </Field>
            )}
          </div>
          <QueryState query={assets} empty={!items.length}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>자산 식별자</th>
                    <th>Namespace</th>
                    <th>식별 상태</th>
                    <th>관측 시각</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((a) => (
                    <tr key={str(a.id)}>
                      <td>{str(a.subject_key)}</td>
                      <td>{str(obj(a.attributes).namespace, '—')}</td>
                      <td>
                        <Badge status={str(a.identity_status, 'unknown')} />
                      </td>
                      <td>{formatDate(str(a.observed_at))}</td>
                      <td>
                        <button className="button" onClick={() => setSelected(a)}>
                          관측 보기
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </QueryState>
          <More query={assets} />
        </Panel>
      )}
      {selected && <AssetDetails row={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
function AssetDetails({ row, onClose }: { row: Row; onClose: () => void }) {
  const app = useApp(),
    target = assetTarget(row);
  const [queryId, setQueryId] = useState(
    str(row.subject_kind) === 'pod'
      ? 'pod_status'
      : str(row.subject_kind) === 'gpu'
        ? 'gpu_utilization'
        : 'node_metrics',
  );
  const q = useResource('/observations/query', {
    scope: app.scope,
    time_range: app.timeRange,
    timezone: 'Asia/Seoul',
    target,
    query_id: queryId,
  });
  const mappings = useResource('/mappings/query', {
    scope: app.scope,
    time_range: app.timeRange,
    target,
  });
  return (
    <Modal wide title="자산 관측 상세" onClose={onClose}>
      <div className="stack">
        <h3>{str(row.subject_key)}</h3>
        <DataView value={row.attributes} />
        <Field label="관측 항목">
          <select value={queryId} onChange={(e) => setQueryId(e.target.value)}>
            {[
              'gpu_utilization',
              'gpu_memory',
              'node_metrics',
              'pod_status',
              'resource_catalog',
              'collection_quality',
              'logs',
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </Field>
        <QueryState query={q}>
          <DataView value={q.data} />
        </QueryState>
        <h3>할당·매핑 관측</h3>
        <QueryState query={mappings}>
          <DataView value={mappings.data} />
        </QueryState>
      </div>
    </Modal>
  );
}
