import { useState, type FormEvent } from 'react';
import { Badge, Field, Modal, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { CommandError, DataView, More, QueryState } from '../components/live';
import {
  num,
  obj,
  rows,
  str,
  strings,
  useCommand,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { useApp } from '../lib/store';
const tabs = [
  { to: '/settings/models', label: '사내 모델' },
  { to: '/settings/routing', label: '질의·Agent별 모델 지정' },
  { to: '/settings/data', label: '데이터 연결' },
  { to: '/settings/backend', label: '백엔드 연결' },
];
export function Settings({ view }: { view: string }) {
  return (
    <div className="page">
      <PageHead
        eyebrow="CONNECTIONS & SETTINGS"
        title="연결·설정"
        description="서버에 저장된 모델 연결, 라우팅을 관리합니다."
      />
      <NavTabs items={tabs} />
      {view === 'models' ? <Models /> : view === 'routing' ? <Routing /> : <DataSettings />}
    </div>
  );
}
function Models() {
  const app = useApp(),
    q = useList('/models?limit=50'),
    cmd = useCommand();
  const [editing, setEditing] = useState<Row | null>(null),
    [test, setTest] = useState<Row | null>(null);
  return (
    <>
      <Panel
        title="등록된 모델"
        action={
          app.canManage && (
            <button className="button primary" onClick={() => setEditing({})}>
              모델 등록
            </button>
          )
        }
      >
        <QueryState query={q} empty={!q.items.length}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>모델</th>
                  <th>연결 주소</th>
                  <th>상태</th>
                  <th>revision</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {q.items.map((m) => (
                  <tr key={str(m.id)}>
                    <td>
                      {str(m.name)}
                      <small className="cell-sub">{str(m.model_name)}</small>
                    </td>
                    <td>{str(m.endpoint_url)}</td>
                    <td>
                      <Badge
                        status={m.enabled ? 'available' : 'unknown'}
                        label={m.enabled ? '사용' : '비활성'}
                      />
                    </td>
                    <td>{num(m.revision)}</td>
                    <td>
                      <div className="head-actions">
                        <button className="button" onClick={() => setEditing(m)}>
                          편집
                        </button>
                        <button
                          className="button"
                          disabled={cmd.busy}
                          onClick={async () => {
                            setTest(null);
                            const r = await cmd.run(
                              `/models/${str(m.id)}/test-connection`,
                              {
                                revision: num(m.revision),
                              },
                              { version: num(m.version) },
                            );
                            if (r) setTest(r);
                          }}
                        >
                          연결 검사
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
        <More query={q} />
        <div className="live-padding">
          <CommandError error={cmd.error} />
          {test && (
            <>
              <h3>연결 검사 결과</h3>
              <DataView value={test} />
              <Notice>전송·응답 형식 검사 결과입니다. 추론 품질은 별도로 검증해야 합니다.</Notice>
            </>
          )}
        </div>
      </Panel>
      {editing && <ModelForm initial={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
function ModelForm({ initial, onClose }: { initial: Row; onClose: () => void }) {
  const cmd = useCommand(),
    app = useApp();
  const [draft, setDraft] = useState<Row>({
      ...initial,
      limits_profile_id: initial.limits_profile_id || 'C07',
      enabled: initial.enabled ?? true,
    }),
    [secret, setSecret] = useState(''),
    [capabilities, setCapabilities] = useState(JSON.stringify(initial.capabilities || {}, null, 2));
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const cap = JSON.parse(capabilities);
      if (!cap || Array.isArray(cap) || typeof cap !== 'object')
        throw new Error('모델 기능은 JSON 객체여야 합니다.');
      const body: Row = { enabled: draft.enabled, capabilities: cap };
      [
        'name',
        'endpoint_url',
        'model_name',
        'artifact_revision',
        'engine_revision',
        'precision',
        'limits_profile_id',
      ].forEach((k) => (body[k] = str(draft[k]).trim()));
      if (secret.trim()) body.secret_ref = secret.trim();
      if (
        await cmd.run(initial.id ? `/models/${str(initial.id)}` : '/models', body, {
          method: initial.id ? 'PATCH' : 'POST',
          version: initial.id ? num(initial.version) : undefined,
        })
      ) {
        app.notify('모델 설정을 저장했습니다.');
        onClose();
      }
    } catch (e) {
      cmd.setError(e instanceof Error ? e.message : '입력값을 확인해 주세요.');
    }
  };
  return (
    <Modal
      wide
      title={initial.id ? '모델 편집' : '모델 등록'}
      onClose={() => {
        if (!cmd.busy) onClose();
      }}
      confirmClose="입력 중인 변경을 버리고 닫을까요?"
    >
      <form className="stack" onSubmit={save}>
        <div className="form-grid">
          {[
            ['name', '표시 이름'],
            ['endpoint_url', '모델 API 주소'],
            ['model_name', '모델 이름'],
            ['artifact_revision', '모델 아티팩트 revision'],
            ['engine_revision', '추론 엔진 revision'],
            ['precision', '정밀도'],
            ['limits_profile_id', '운영 한도 프로필'],
          ].map(([k, l]) => (
            <Field key={k} label={l}>
              <input
                required
                type={k === 'endpoint_url' ? 'url' : 'text'}
                value={str(draft[k])}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            </Field>
          ))}
        </div>
        <Field
          label="Secret 참조"
          hint="비밀 값 자체가 아닌 서버의 Secret 참조를 입력합니다. 비워 두면 기존 참조를 유지합니다."
        >
          <input value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="모델 기능 (JSON)">
          <textarea
            rows={3}
            value={capabilities}
            onChange={(e) => setCapabilities(e.target.value)}
          />
        </Field>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.enabled === true}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          사용
        </label>
        <Notice>연결 주소는 백엔드에 등록된 허용 호스트여야 합니다.</Notice>
        <CommandError error={cmd.error} />
        <button className="button primary" disabled={cmd.busy || !app.canManage}>
          {cmd.busy ? '저장 중…' : '모델 저장'}
        </button>
      </form>
    </Modal>
  );
}
function Routing() {
  const q = useResource('/model-routes'),
    models = useList('/models?limit=200');
  return (
    <Panel title="모델 라우팅" description="모델 ID와 revision을 함께 고정해 저장합니다.">
      <QueryState query={q}>
        <QueryState query={models}>
          <RouteEditor key={num(q.data?.version)} initial={q.data || {}} models={models.items} />
          <More query={models} />
        </QueryState>
      </QueryState>
    </Panel>
  );
}
function RouteEditor({ initial, models }: { initial: Row; models: Row[] }) {
  const cmd = useCommand(),
    app = useApp();
  const [draft, setDraft] = useState<Row>(() =>
    Object.fromEntries(['rca', 'report'].filter((k) => initial[k]).map((k) => [k, initial[k]])),
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await cmd.run('/model-routes', draft, { method: 'PATCH', version: num(initial.version) }))
      app.notify('모델 라우팅을 저장했습니다.');
  };
  return (
    <form className="live-padding stack" onSubmit={submit}>
      {[
        ['rca', 'RCA'],
        ['report', '보고서'],
      ].map(([k, l]) => {
        const ref = obj(draft[k]),
          value = ref.model_id ? `${str(ref.model_id)}:${num(ref.model_revision)}` : '';
        return (
          <Field key={k} label={l}>
            <select
              value={value}
              onChange={(e) => {
                const next = { ...draft };
                if (e.target.value) {
                  const [id, revision] = e.target.value.split(':');
                  next[k] = { model_id: id, model_revision: +revision };
                } else next[k] = null;
                setDraft(next);
              }}
            >
              <option value="">모델 미지정</option>
              {value && !models.some((m) => `${str(m.id)}:${num(m.revision)}` === value) && (
                <option value={value}>저장된 모델 · revision {num(ref.model_revision)}</option>
              )}
              {models
                .filter((m) => m.enabled)
                .map((m) => (
                  <option key={str(m.id)} value={`${str(m.id)}:${num(m.revision)}`}>
                    {str(m.name)} · revision {num(m.revision)}
                  </option>
                ))}
            </select>
          </Field>
        );
      })}
      <CommandError error={cmd.error} />
      <button className="button primary" disabled={cmd.busy || !app.canManage}>
        라우팅 저장
      </button>
    </form>
  );
}
function DataSettings() {
  const modules = useResource('/service-status'),
    clusters = useList('/clusters');
  return (
    <div className="stack">
      <Panel title="서비스 연결 상태">
        <QueryState query={modules}>
          <div className="backend-modules">
            {rows(modules.data?.items).map((m) => (
              <div className="backend-module" key={str(m.module)}>
                <strong>
                  {(
                    {
                      job_controller: 'Job Controller',
                      incident: '사건·알림',
                    } as Record<string, string>
                  )[str(m.module)] || str(m.module)}
                </strong>
                <Badge status={str(m.status)} />
              </div>
            ))}
          </div>
        </QueryState>
      </Panel>
      <Panel title="관측 CPC">
        <QueryState query={clusters}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>CPC</th>
                  <th>Namespace</th>
                  <th>수집 상태</th>
                </tr>
              </thead>
              <tbody>
                {clusters.items.map((c) => (
                  <tr key={str(c.id)}>
                    <td>{str(c.cluster_id)}</td>
                    <td>
                      {c.namespaces === null ? '전체 Namespace' : strings(c.namespaces).join(', ')}
                    </td>
                    <td>
                      <Badge status={str(c.collection_status, 'unknown')} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
      </Panel>
      <Panel title="큐·Worker·용량 상태">
        <QueryState query={modules}>
          <div className="live-padding">
            <DataView value={{ queue: modules.data?.queue, scheduler: modules.data?.scheduler }} />
            <Notice>실행 용량은 운영 환경에서 설정합니다.</Notice>
          </div>
        </QueryState>
      </Panel>
    </div>
  );
}
