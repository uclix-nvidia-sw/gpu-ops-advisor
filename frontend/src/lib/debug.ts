import { obj, rows, str, type Row } from './live';

export const debugTabs = [
  ['input', '입력·출처', '무엇을 분석하도록 접수됐나요?'],
  ['execution', '실행·시도', '어느 시도에서 어떤 상태가 됐나요?'],
  ['evidence', '근거·데이터', '어떤 데이터를 사용했고 무엇이 부족한가요?'],
  ['result', '결과·공개', '어떤 결과가 공개됐나요?'],
] as const;
export type DebugTab = (typeof debugTabs)[number][0];
export function debugTab(value: string | null): DebugTab {
  return debugTabs.find(([key]) => key === value)?.[0] || 'input';
}
// Only app-local list/detail destinations are accepted as return locations.
export function returnPath(value: unknown, fallback = '/jobs'): string {
  return typeof value === 'string' &&
    /^\/(jobs|cases|reports|schedules|incidents|analyses|dashboard)(?:[/?#]|$)/.test(value) &&
    !/[\\\r\n]/.test(value)
    ? value
    : fallback;
}
export function debugPath(id: string, tab: DebugTab, from?: string) {
  const params = new URLSearchParams({ tab });
  if (from) params.set('from', returnPath(from));
  return `/jobs/${encodeURIComponent(id)}?${params}`;
}

export type Relation = {
  title: string;
  value: string;
  source: string;
  join: string;
  purpose: string;
  note: string;
  record?: Row;
  path?: string;
  expected?: Row;
  href?: string;
  unavailable?: string;
};

export function jobRelation(job: Row, key: string, attempt?: number, trace?: Row): Relation {
  const id = str(job.id);
  const result = job.result_ref != null ? obj(job.result) : {};
  const traceKey = (
    { snapshot: 'incident_snapshot', request: 'outbox', result: 'publication' } as Record<
      string,
      string
    >
  )[key];
  const linked = obj(trace?.[traceKey]);
  if (linked.state === 'available') {
    const base = jobRelation(job, key, attempt);
    return {
      ...base,
      value:
        key === 'snapshot'
          ? `${str(trace?.incident_id)} / revision ${trace?.evidence_version}`
          : key === 'request'
            ? str(trace?.source_key)
            : base.value,
      note:
        key === 'snapshot'
          ? '작업에 고정된 revision 원본입니다. 현재 사건의 최신 버전과 다를 수 있습니다.'
          : key === 'request'
            ? 'source_module·source_key와 job_id로 연결한 전달 기록입니다. accepted는 접수이며 실행 성공이 아닙니다.'
            : '공개된 후보 행의 검증·버전·해시입니다. 미공개 후보 본문은 제공하지 않습니다.',
      record: obj(linked.record),
      unavailable: undefined,
    };
  }
  switch (key) {
    case 'incident':
      return {
        title: '이 작업의 원본 사건',
        value: str(job.incident_id, 'API 미제공'),
        source: 'jobs.input_snapshot.incident_id → API incident_id',
        join: 'jobs.incident_id = incidents.id',
        purpose:
          'RCA가 시작된 알람과 발생 대상을 확인합니다. 하나의 사건에 여러 RCA 작업이 연결될 수 있습니다.',
        note: '조회되는 것은 현재 사건입니다. 실행 당시 증거는 별도의 incident_evidence_versions 스냅샷입니다.',
        ...(str(job.incident_id)
          ? {
              path: `/incidents/${encodeURIComponent(str(job.incident_id))}`,
              expected: { id: job.incident_id },
              href: `/incidents/${encodeURIComponent(str(job.incident_id))}`,
            }
          : { unavailable: '사건 식별자가 API에 제공되지 않았습니다.' }),
      };
    case 'snapshot':
      return {
        title: '실행 당시 사건 증거',
        value: `${str(job.incident_id, '사건 미확인')} + revision 미제공`,
        source: 'jobs.incident_id + jobs.evidence_version',
        join: '(incident_id, evidence_version) = incident_evidence_versions.(incident_id, revision)',
        purpose:
          'Worker가 조사 입력으로 읽은 불변 스냅샷입니다. 사건 ID만으로는 사용한 버전을 특정할 수 없습니다.',
        note: '현재 사건의 evidence_version으로 과거 작업의 revision을 대신하지 않습니다.',
        unavailable:
          '입력·출처의 연결 추적 조회 상태를 확인하세요. 고정 스냅샷을 읽지 못하면 현재 사건의 revision으로 대체하지 않습니다.',
      };
    case 'parent':
      return {
        title: '이전 작업',
        value: str(job.parent_job_id, '연결 없음'),
        source: 'jobs.parent_job_id',
        join: 'jobs.parent_job_id = jobs.id (이전 작업)',
        purpose:
          '새 조건으로 생성한 작업과 이전 작업을 연결합니다. 같은 작업의 자동 재시도와는 다릅니다.',
        note: '이전 작업의 요청 조건과 현재 작업의 조건을 비교하세요.',
        ...(str(job.parent_job_id)
          ? {
              path: `/jobs/${encodeURIComponent(str(job.parent_job_id))}`,
              expected: { id: job.parent_job_id },
              href: debugPath(str(job.parent_job_id), 'input', debugPath(id, 'input')),
            }
          : { unavailable: '이 작업에 이전 작업 참조가 없습니다.' }),
      };
    case 'attempt': {
      const record = rows(job.attempts).find((a) => a.attempt_no === attempt);
      return {
        title: '선택한 실행 시도',
        value: `${id} / 시도 ${attempt ?? '미확인'}`,
        source: 'API attempts[] ← job_attempts',
        join: 'job_attempts.job_id = jobs.id AND attempt_no = 선택한 시도',
        purpose:
          '한 작업의 실행·재시도를 구분하는 복합 키입니다. attempt_no만으로 다른 작업과 연결하면 안 됩니다.',
        note: '시도별 시작·종료·단계·종료 사유만 제공됩니다. worker_id·boot_id·lease는 이 API에 없습니다.',
        ...(record
          ? { record: { job_id: id, ...record } }
          : {
              unavailable:
                '선택한 실행 시도가 응답에 없습니다. 접수 대기라면 아직 실행 전일 수 있습니다.',
            }),
      };
    }
    case 'result':
      return {
        title: 'JC가 공개한 결과',
        value: str(job.result_ref, '미공개'),
        source: 'API result_ref ← jobs.published_result_id',
        join: 'published_result_id = result_candidates.id AND job_id = jobs.id AND kind = jobs.kind',
        purpose:
          'Worker가 저장한 후보 중 JC가 공개한 결과를 선택합니다. result_ref는 작업 ID가 아닌 후보 행의 ID입니다.',
        note: 'API result는 result_candidates.body입니다. 미공개 후보나 후보 행의 attempt_no·content_hash는 제공되지 않습니다.',
        ...(job.result_ref != null
          ? { record: result }
          : {
              unavailable: '아직 공개된 결과가 없습니다. 미공개 후보의 존재 여부는 알 수 없습니다.',
            }),
      };
    case 'request':
      return {
        title: '보고서 요청의 출처',
        value: 'source_module / source_key 미제공',
        source: 'jobs.source_module + jobs.source_key',
        join: '즉시: manual_report_intents.source_key / 정기: schedule_occurrences.job_id = jobs.id',
        purpose:
          '즉시 요청인지 정기 일정의 어느 회차인지 확인하는 연결입니다. 정기 회차는 schedule_id + revision으로 실행 당시 일정 조건을 찾습니다.',
        note: '정기 경로: schedule_revisions → schedule_occurrences → enqueue_outbox → jobs. accepted는 접수이며 실행 성공이 아닙니다.',
        unavailable:
          '입력·출처의 연결 추적에서 즉시 요청·정기 회차를 확인하세요. outbox가 없는 즉시 요청은 manual_report_intents에 보존됩니다.',
        href: '/schedules',
      };
    case 'model': {
      const model = obj(obj(result.versions).model);
      return {
        title: '실행에 고정된 모델 설정',
        value: `${str(model.model_id, '모델 미제공')} / revision ${model.model_revision ?? '미제공'}`,
        source: 'result.versions.model.model_id + model_revision',
        join: 'model_id = profile_revisions.profile_id AND model_revision = profile_revisions.revision',
        purpose:
          'Worker가 실행할 때 읽은 모델 설정 스냅샷을 식별합니다. 현재 서비스 프로필과 다를 수 있습니다.',
        note: '모델 키가 기록되어 있어도 실제 LLM 호출 성공을 의미하지 않습니다. llm_usage·narrative_status와 함께 확인하세요.',
        record: model,
        unavailable:
          '고정된 식별자는 위에 표시합니다. 해당 profile_revisions.snapshot을 읽는 API는 현재 제공되지 않습니다.',
      };
    }
    default:
      return {
        title: '현재 작업',
        value: id,
        source: 'API id ← jobs.id',
        join: 'jobs.id → job_attempts.job_id / evidence.job_id / result_candidates.job_id',
        purpose:
          'JC가 관리하는 실행 단위입니다. 입력, 여러 실행 시도, 수집 근거와 공개 결과를 묶습니다.',
        note: 'API는 DB 행의 일부 필드와 가공된 공개 결과를 반환합니다. 전체 DB 행이 아닙니다.',
        record: Object.fromEntries(
          ['id', 'kind', 'status', 'stage', 'attempt_no', 'created_at', 'result_ref'].map((k) => [
            k,
            job[k],
          ]),
        ),
      };
  }
}

export function knowledgeRelation(knowledge: Row): Relation {
  const id = str(knowledge.knowledge_id);
  const revision = knowledge.revision;
  return {
    title: '실행에 고정된 지식 버전',
    value: `${id || 'ID 미제공'} / revision ${revision ?? '미제공'}`,
    source: 'result.versions.knowledge[]',
    join: '(knowledge_id, revision) = knowledge_revisions.(knowledge_id, revision); content_hash 일치 확인',
    purpose:
      'RCA 입력에 고정된 Runbook 후보의 본문을 읽습니다. 실제 선택·사용 여부는 수집 근거의 runbook_selection 기록과 대조하세요.',
    note: 'knowledge_id는 문서, knowledge_revisions.id는 특정 버전 행입니다. 최신 버전으로 대체하지 않습니다.',
    ...(id && typeof revision === 'number' && str(knowledge.content_hash)
      ? {
          path: `/knowledge/${encodeURIComponent(id)}/revisions/${revision}`,
          expected: { knowledge_id: id, revision, content_hash: knowledge.content_hash },
        }
      : { unavailable: '정확한 지식 ID·revision·content_hash가 없어 연결을 검증할 수 없습니다.' }),
  };
}

export function evidenceRelation(job: Row, id: string, diagnostic = false): Relation {
  return {
    title: diagnostic ? '선택한 시도의 조회 요청·응답' : '공개 결과가 참조한 수집 근거',
    value: id,
    source: diagnostic ? 'evidence.(job_id, attempt_no)' : 'result_candidates.body.evidence_refs[]',
    join: `evidence.id = 선택한 근거; evidence.job_id = jobs.id; evidence.attempt_no = ${diagnostic ? '선택한 시도' : '작업의 현재 시도'}`,
    purpose: '계산·판단에 사용한 저장 근거를 조회하고 동일한 작업·시도에 속하는지 대조합니다.',
    note: diagnostic
      ? 'query_id는 조회 종류, evidence.id는 저장 행입니다. input은 저장된 조회 인자, snapshot은 당시 응답입니다. 실행 비밀·내부 object_key는 제외합니다. created_at은 실행 시각이 아닙니다.'
      : 'query_id는 조회 종류입니다. 실제 근거 행은 evidence.id로 구분합니다. input·object_key는 일반 API가 제외합니다.',
    path: diagnostic
      ? `/jobs/${encodeURIComponent(str(job.id))}/evidence/${encodeURIComponent(id)}?attempt=${job.attempt_no}`
      : `/evidence/${encodeURIComponent(id)}`,
    expected: {
      id,
      job_id: job.id,
      ...(typeof job.attempt_no === 'number' ? { attempt_no: job.attempt_no } : {}),
    },
  };
}
export function relationMismatch(record: Row, expected?: Row) {
  return expected ? Object.keys(expected).filter((key) => record[key] !== expected[key]) : [];
}
