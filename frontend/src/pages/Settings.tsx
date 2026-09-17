import { Cable, Cpu, Database, FlaskConical, Network, Plus, Save, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Badge, Field, Modal, NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { useApp, useDatabase } from '../lib/store';
import type { Model } from '../lib/types';
const tabs = [
  { to: '/settings/models', label: '사내 모델' },
  { to: '/settings/routing', label: '질의·Agent별 모델 지정' },
  { to: '/settings/data', label: '데이터 연결' },
];
export function Settings({ view }: { view: 'models' | 'routing' | 'data' }) {
  const app = useApp();
  const { db, mutate } = useDatabase();
  const [edit, setEdit] = useState<Model | null>(null);
  const [error, setError] = useState('');
  const [testing, setTesting] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const [routing, setRouting] = useState<Record<string, string> | null>(null);
  const [dataEdit, setDataEdit] = useState('');
  const [profile, setProfile] = useState({ endpoint: '', secret_ref: '', interval: '15' });
  const manager = app.role === 'admin';
  if (!db) return <div className="loading">설정 조회 중…</div>;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (!edit) return;
      const url = new URL(edit.endpoint_url);
      if (
        !['http:', 'https:'].includes(url.protocol) ||
        url.username ||
        url.password ||
        url.search ||
        url.hash
      )
        throw new Error(
          'HTTP(S) Endpoint를 입력하세요. URL에 인증정보·쿼리·fragment를 넣을 수 없습니다.',
        );
      if (!edit.name.trim() || !edit.model_name.trim())
        throw new Error('별칭과 추론용 모델 ID를 입력해 주세요.');
      await mutate((d) => {
        const model = d.models.find((m) => m.id === edit.id);
        if (model) {
          if (model.version !== edit.version)
            throw new Error(
              '설정 버전이 변경되었습니다. 입력을 보존하고 최신 설정과 비교해 주세요.',
            );
          Object.assign(model, { ...edit, version: model.version + 1 });
        } else d.models.push(edit);
      });
      setEdit(null);
      app.notify('데모 모델 설정이 저장되었습니다. 실제 연결은 아직 검증되지 않았습니다.');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="page">
      <PageHead
        eyebrow="CONNECTIONS & SETTINGS"
        title="연결·설정"
        description="사내 모델과 데이터 연결을 관리하고, 각 업무에 적합한 모델을 지정합니다."
        actions={
          view === 'models' &&
          manager && (
            <button
              className="button primary"
              onClick={() => {
                setError('');
                setEdit({
                  id: crypto.randomUUID(),
                  name: '',
                  endpoint_url: '',
                  model_name: '',
                  artifact_revision: '',
                  engine_revision: '',
                  precision: 'BF16',
                  enabled: true,
                  version: 1,
                });
              }}
            >
              <Plus size={16} />
              사내 모델 등록
            </button>
          )
        }
      />
      <NavTabs items={tabs} />
      {!manager && (
        <Notice>
          설정은 읽기 전용입니다. 데모 사용자 메뉴에서 서비스 관리자 역할로 변경하면 편집 흐름을
          확인할 수 있습니다.
        </Notice>
      )}
      {view === 'models' && (
        <>
          <Notice>
            모델 설정 저장, 서버 연결 검사, 분석 품질 검증은 서로 다른 단계입니다. 브라우저가 모델
            Endpoint에 직접 접속하지 않습니다.
          </Notice>
          <div className="model-grid">
            {db.models.map((m) => (
              <Panel key={m.id}>
                <div className="model-card">
                  <div className="model-top">
                    <span className="model-icon">
                      <Cpu size={25} />
                    </span>
                    <Badge
                      status={m.enabled ? 'ready' : 'neutral'}
                      label={m.enabled ? '활성' : '비활성'}
                    />
                  </div>
                  <h2>{m.name}</h2>
                  <p className="mono">{m.model_name}</p>
                  <dl className="details">
                    <dt>Endpoint</dt>
                    <dd className="mono">{m.endpoint_url}</dd>
                    <dt>프로필 ID</dt>
                    <dd>{m.id}</dd>
                    <dt>설정 revision</dt>
                    <dd>v{m.version}</dd>
                    <dt>지정 업무</dt>
                    <dd>
                      {Object.entries(db.routes)
                        .filter(([, v]) => v === m.id)
                        .map(([k]) => k)
                        .join(' · ') || '개별 지정 없음'}
                    </dd>
                    <dt>서버 연결</dt>
                    <dd>
                      <Badge status="blocked" label="미검증" />
                    </dd>
                    <dt>분석 품질</dt>
                    <dd>
                      <Badge status="blocked" label="미검증 · T40" />
                    </dd>
                  </dl>
                  {tested === m.id && (
                    <Notice tone="warning">
                      백엔드 API가 연결되지 않아 서버 연결 검사를 실행할 수 없습니다. 설정은
                      유지됩니다.
                    </Notice>
                  )}
                  <div className="model-actions">
                    <button
                      className="button"
                      disabled={!manager || testing === m.id}
                      onClick={() => {
                        setTesting(m.id);
                        setTimeout(() => {
                          setTested(m.id);
                          setTesting(null);
                        }, 450);
                      }}
                    >
                      <FlaskConical size={15} />
                      {testing === m.id ? '확인 중…' : '연결 검사'}
                    </button>
                    <button
                      className="button"
                      disabled={!manager}
                      onClick={() => {
                        setEdit({ ...m });
                        setError('');
                      }}
                    >
                      수정
                    </button>
                    <button
                      className="text-button"
                      disabled={!manager}
                      onClick={async () => {
                        if (m.enabled && Object.values(db.routes).includes(m.id)) {
                          app.notify(
                            '사용 중인 모델입니다. 모델 지정에서 대체 모델을 저장한 뒤 비활성화하세요.',
                          );
                          return;
                        }
                        await mutate((d) => {
                          const item = d.models.find((x) => x.id === m.id)!;
                          item.enabled = !item.enabled;
                          item.version++;
                        });
                      }}
                    >
                      {m.enabled ? '비활성화' : '활성화'}
                    </button>
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        </>
      )}
      {view === 'routing' && (
        <>
          <Panel
            title="업무별 모델 지정"
            description="개별 지정하지 않은 전문 Agent는 공통 기본 모델을 상속합니다."
          >
            <div className="routing-list">
              {[
                ['assistant', '공통 Assistant', '일반 설명과 가벼운 조회'],
                ['rca', 'RCA Agent', '사건·직접 요청의 근거 조사'],
                ['report', '운영 보고서 Agent', '기간 집계와 운영 설명'],
              ].map(([key, label, description]) => (
                <div className="routing-row" key={key}>
                  <span className="routing-icon">
                    <Network size={22} />
                  </span>
                  <div>
                    <h3>{label}</h3>
                    <p>{description}</p>
                  </div>
                  <Field label={`${label} 모델`}>
                    <select
                      disabled={!manager}
                      value={(routing || db.routes)[key]}
                      onChange={(e) =>
                        setRouting({ ...(routing || db.routes), [key]: e.target.value })
                      }
                    >
                      {key !== 'assistant' && <option value="inherit">공통 기본 모델 상속</option>}
                      {db.models
                        .filter((m) => m.enabled)
                        .map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} · v{m.version}
                          </option>
                        ))}
                    </select>
                  </Field>
                </div>
              ))}
            </div>
            <div className="panel-body">
              <Notice>
                변경 내용은 새 작업에 적용됩니다. 진행 중인 작업과 과거 결과의 모델 revision은
                유지됩니다.
              </Notice>
            </div>
          </Panel>
          <div className="form-actions">
            <button
              className="button primary"
              disabled={!manager || !routing}
              onClick={async () => {
                await mutate((d) => {
                  d.routes = routing!;
                });
                setRouting(null);
                app.notify('새 작업에 적용할 모델 지정이 저장되었습니다.');
              }}
            >
              <Save size={15} />
              모델 지정 저장
            </button>
          </div>
        </>
      )}
      {view === 'data' && (
        <>
          <div className="connection-path">
            <div>
              <Database size={22} />
              <b>CPC 수집</b>
              <small>GPU Exporter · Kubernetes</small>
            </div>
            <span>→</span>
            <div>
              <Cable size={22} />
              <b>관측 Gateway</b>
              <small>Alloy 수집·전송</small>
            </div>
            <span>→</span>
            <div>
              <Database size={22} />
              <b>중앙 관측</b>
              <small>Mimir · Loki</small>
            </div>
            <span>→</span>
            <div>
              <ShieldCheck size={22} />
              <b>Backend API</b>
              <small>권한·조회·집계</small>
            </div>
          </div>
          <Panel
            title="데이터 연결 프로필"
            description="수신 상태와 분석 데이터의 충분성은 자산·관측에서 별도로 확인합니다."
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>프로필</th>
                    <th>연결 경로</th>
                    <th>수집 주기</th>
                    <th>원천 갱신</th>
                    <th>검증 상태</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Mimir 메트릭', 'mimir.internal.example', '15초', '소스별 상이'],
                    ['Loki 로그', 'loki.internal.example', '이벤트 기반', '최신 수신 미확인'],
                    ['Kubernetes 관계', 'ksm.internal.example', '30초', '동시점 UID 일부 확인'],
                  ].map((r) => (
                    <tr key={r[0]}>
                      <td>
                        <b>{r[0]}</b>
                      </td>
                      <td className="mono">{r[1]}</td>
                      <td>{r[2]}</td>
                      <td>{r[3]}</td>
                      <td>
                        <Badge status="blocked" label="실환경 확인 필요" />
                      </td>
                      <td>
                        <button
                          disabled={!manager}
                          className="button"
                          onClick={() => {
                            setDataEdit(r[0]);
                            setProfile({
                              endpoint: `https://${r[1]}`,
                              secret_ref: '',
                              interval: r[2] === '30초' ? '30' : '15',
                            });
                            setError('');
                          }}
                        >
                          설정
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Notice>
            권한 관리는 별도 manage_access 권능이 필요합니다. 서비스 관리자에게 전체 CPC 관측이나
            권한 변경 권능을 자동 부여하지 않습니다.
          </Notice>
        </>
      )}
      {edit && (
        <Modal
          title={db.models.some((m) => m.id === edit.id) ? '사내 모델 수정' : '사내 모델 등록'}
          onClose={() => setEdit(null)}
          confirmClose="입력 창을 닫을까요? 저장하지 않은 변경은 사라집니다."
          wide
        >
          <form className="stack" onSubmit={save}>
            <div className="form-grid">
              <Field label="별칭 *">
                <input
                  required
                  value={edit.name}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                  placeholder="예: 사내 RCA 모델"
                />
              </Field>
              <Field label="추론용 모델 ID *">
                <input
                  required
                  value={edit.model_name}
                  onChange={(e) => setEdit({ ...edit, model_name: e.target.value })}
                  placeholder="internal-instruct"
                />
              </Field>
            </div>
            <Field label="Endpoint URL *" hint="모델 프로필 ID와 추론용 모델 ID는 별개입니다.">
              <input
                required
                type="url"
                value={edit.endpoint_url}
                onChange={(e) => setEdit({ ...edit, endpoint_url: e.target.value })}
                placeholder="https://inference.internal.example/v1"
              />
            </Field>
            <details open>
              <summary>고급 설정</summary>
              <div className="stack advanced-fields">
                <div className="form-grid">
                  <Field label="Artifact revision">
                    <input
                      value={edit.artifact_revision}
                      onChange={(e) => setEdit({ ...edit, artifact_revision: e.target.value })}
                    />
                  </Field>
                  <Field label="Engine revision">
                    <input
                      value={edit.engine_revision}
                      onChange={(e) => setEdit({ ...edit, engine_revision: e.target.value })}
                    />
                  </Field>
                  <Field label="정밀도">
                    <select
                      value={edit.precision}
                      onChange={(e) => setEdit({ ...edit, precision: e.target.value })}
                    >
                      {['BF16', 'FP16', 'FP8', 'INT8', 'INT4'].map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Secret 참조" hint="비밀 원문을 입력하지 마세요.">
                    <input
                      value={edit.secret_ref || ''}
                      onChange={(e) => setEdit({ ...edit, secret_ref: e.target.value })}
                      placeholder="secret://model-api-token"
                    />
                  </Field>
                </div>
              </div>
            </details>
            <Notice>
              최종 허용 목적지·비밀 검증·예산 프로필은 백엔드 통합 시 검사합니다. 외부 상용 모델로
              자동 우회하지 않습니다.
            </Notice>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary">모델 설정 저장</button>
          </form>
        </Modal>
      )}
      {dataEdit && (
        <Modal title={`${dataEdit} 설정`} onClose={() => setDataEdit('')}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setError(
                '데이터 연결 설정 API가 아직 연결되지 않았습니다. 입력은 창을 닫기 전까지 유지됩니다.',
              );
            }}
          >
            <Field label="Endpoint">
              <input
                required
                type="url"
                value={profile.endpoint}
                onChange={(e) => setProfile({ ...profile, endpoint: e.target.value })}
              />
            </Field>
            <Field label="Secret 참조">
              <input
                value={profile.secret_ref}
                onChange={(e) => setProfile({ ...profile, secret_ref: e.target.value })}
                placeholder="secret://observations-token"
              />
            </Field>
            <Field label="수집 주기 (초)">
              <input
                min="1"
                required
                type="number"
                value={profile.interval}
                onChange={(e) => setProfile({ ...profile, interval: e.target.value })}
              />
            </Field>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <Notice>프론트엔드에서 관측 소스로 직접 접속하지 않습니다.</Notice>
            <button className="button primary">설정 저장 요청</button>
          </form>
        </Modal>
      )}
    </div>
  );
}
