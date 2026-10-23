import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { NavTabs, Notice, PageHead, Panel } from '../components/ui';
import { topicId, topics } from '../lib/live';
import { reportKinds, topicDisplayBases } from '../lib/reportKinds';
import { reportTabs } from '../lib/reportNavigation';
import { advicePresentation } from '../lib/namespaceAdvice';
import '../lib/advice-colors.css';

const adviceGuides = [
  [
    'capacity_review',
    'GPU 활동이 높고 대기 Pod도 있던 관측 구간입니다. 실제 GPU 부족인지와 할당·운영정책을 확인한 뒤 추가 할당을 검토합니다.',
  ],
  [
    'schedule_candidate',
    '낮은 활동 기준에 해당했던 구간만 표시합니다. 다른 구간보다 여유롭다는 비교는 아닙니다. 이후 같은 시간대의 반복성과 가용 GPU를 확인해 일부 작업을 시험할지 판단합니다.',
  ],
  [
    'relative_activity',
    '같은 Namespace의 비교 구간과 낮은 활동 구간을 나란히 표시합니다. 지난 관측이므로 앞으로도 같은지 확인한 뒤 시작 시간을 바꿀 수 있는 작업 일부의 시험을 검토합니다.',
  ],
  [
    'queue_review',
    '대기 Pod가 노드를 배정받기 전인지, 노드 배정 뒤 컨테이너 시작을 준비하는 중인지 구분하는 점검입니다. 대기 Pod 수만으로 GPU 부족을 확정하지 않습니다.',
  ],
  [
    'batch_progress',
    '관측 기간의 완료 Job과 남아 있던 대기를 함께 살펴봅니다. Job 경과시간은 대기·준비를 포함하며, 완료가 대기를 줄인 원인이라고 단정하지 않습니다.',
  ],
  [
    'resident_memory',
    'GPU 활동률은 낮지만 장치 메모리 점유가 높았던 관측입니다. 새 작업 배치 전에 어떤 작업이 메모리를 사용했는지 확인하며, 작업 유형 라벨 없이 서빙·학습 목적을 추정하지 않습니다.',
  ],
  [
    'repeated_activity',
    '떨어진 여러 관측 구간을 각각 표시합니다. 관측 사이도 같은 상태였다거나 매일 반복된다고 해석하지 않습니다.',
  ],
];

// Keep current behavior distinct from the development goals in specification 12.
const topicGuides = [
  {
    purpose: '어떤 GPU가 관측됐고 메모리·온도는 어땠는지 확인합니다.',
    examples: [
      '이 기간에 클러스터에서 관측된 GPU는 몇 대인가?',
      '관측된 GPU의 메모리·온도 기록과 Node 조건은 무엇인가?',
    ],
    result:
      '관측 GPU 수, 유효한 시간 계약의 평균과 실제 측정 시각이 미확인인 기록값을 구분합니다. Node 조건 관측도 별도로 표시합니다.',
    inputs: 'GPU 신원, VRAM, 온도 관측이 필요합니다.',
    limit:
      '전체 장비 목록의 완전성이나 장비 추가·제거 이력은 확정하지 않습니다. 장치 VRAM을 Pod의 메모리 실사용량으로 읽지 마세요.',
    next: '누락된 GPU와 원본 지표의 단위를 확인한 뒤 장비 목록·변경 기록과 대조하세요.',
    queries:
      '기본 보고서(criteria 1.3)는 D02 · D03 · D04 · D16 · D20을 사용합니다. 장비 관측에서 쓰지 않는 D06 Pod 신원과 D15 할당 메모리·D18 Node CPU·D19 load는 조회하지 않습니다. O08을 함께 선택하면 그 분석에 필요한 D06은 수집합니다. 이전 기준(criteria 1.2)의 조회와 저장된 결과는 유지합니다.',
  },
  {
    purpose: 'GPU가 작업에 얼마나 할당됐는지 확인합니다.',
    examples: [
      '분석 종료 시점에 전용으로 할당돼 있던 GPU는 몇 대인가?',
      '이 기간에 확인된 전용 GPU 할당 시간을 합치면 얼마나 되나?',
    ],
    result:
      '검증된 전용 할당은 종료 시점 할당 GPU 수와 GPU·시간, MIG는 인스턴스·시간으로 표시합니다. GPU–Pod 연결 관측 수·시간도 별도로 제공합니다.',
    inputs: '할당 모드·시작/종료·GPU·Pod 신원을 갖춘 할당 이력과 같은 시각의 관측이 필요합니다.',
    limit:
      'GPU–Pod 연결만으로 전용 할당을 확정하지 않습니다. 할당 이력이 없으면 할당량은 산출 불가여도 연결 관측값은 남을 수 있습니다.',
    next: '할당 이력 지표가 실제로 수집되는지, 전용·공유·MIG 모드가 구분되는지 확인하세요.',
    queries: 'D08 · D01 · D06 · D10',
  },
  {
    purpose: '할당된 GPU 중 활동이 낮아 작업 목적을 확인할 대상을 찾습니다.',
    examples: [
      'GPU를 전용으로 할당받았지만 활동이 낮았던 구간은 어디인가?',
      '담당자에게 대기 목적을 확인할 GPU와 작업은 무엇인가?',
    ],
    result:
      '동일한 전용 할당 구간에서 저활동 시간과 검토 후보를 계산합니다. 현재 기준은 60분 창, 유효 관측 95% 이상, 활동률 5% 미만인 시간이 유효시간의 90% 이상입니다.',
    inputs: '전용 할당 이력, Pod UID와 할당 구간 식별자, 같은 GPU의 활동률이 필요합니다.',
    limit:
      '짧은 구간이나 관측 부족은 후보 판정을 보류합니다. 저활동은 낭비나 회수 가능량이 아닙니다. 현재 작업 목적 확인 권고는 판단 보류 상태로 남습니다.',
    next: '추론 대기·예약·초기화·체크포인트 등 정상적인 대기 목적을 담당자에게 확인하세요.',
    queries: 'D08 · D06 · D02 · D10',
  },
  {
    purpose: '한 Pod에 연결된 여러 GPU의 활동률 차이를 확인합니다.',
    examples: [
      '한 Pod에 연결된 GPU 중 일부만 유난히 적게 활동했나?',
      '같은 작업에 연결된 GPU들의 평균 활동률은 얼마나 차이 나나?',
    ],
    result: '같은 Pod의 GPU들을 공통 관측 시간에 맞춰 평균·최솟값·최댓값·차이(%p)를 계산합니다.',
    inputs: 'Pod별 복수 GPU 할당 이력과 각 GPU의 같은 시각 활동률이 필요합니다.',
    limit:
      '별도 Pod로 나뉜 분산 서비스 전체를 하나의 작업으로 자동 묶지 않습니다. 편차만으로 병목이나 GPU 불량을 확정하지 않습니다.',
    next: '작업 분할, 입력 공급, 통신과 프로파일을 대조해 편차가 정상 역할 차이인지 확인하세요.',
    queries: 'D08 · D06 · D02',
  },
  {
    purpose: '기간 내 기록된 사건과 공개 RCA를 함께 살펴봅니다.',
    examples: [
      '이 기간에 선택한 대상에서 기록된 장애 사건은 몇 건인가?',
      '해당 사건의 공개된 RCA에는 어떤 원인 후보가 제시돼 있나?',
    ],
    result:
      '사건별 알람 기록·공개 RCA·연결된 조치 기록과 다음 확인을 제공합니다. 알람 해제를 복구 완료로 바꾸어 표시하지 않습니다.',
    inputs: '기간·범위에 해당하는 저장 Incident와 공개 RCA 결과를 사용합니다.',
    limit:
      '분석 기간에 발생한 사건만 포함합니다. 기간 이전부터 이어진 사건 전체를 포함하지 않으며 상태는 자료 기준 시각의 기록입니다. 조사 결과·조치 기록만으로 복구를 확정하지 않습니다.',
    next: '장비·사건 종류와 RCA의 원인 판단 수준을 따로 확인하세요. 보고서 요청이 새 RCA를 실행하지는 않습니다.',
    queries:
      '기본 보고서(criteria 1.3)의 통합 D 설정에서는 DB 사건·공개 RCA·연결된 조치 스냅샷만 읽습니다. 계산하지 않는 D10·D22 조회는 생략합니다. 다른 주제에서 필요한 조회는 유지합니다.',
  },
  {
    purpose: '사건 발생 시점에 해당 GPU에 연결됐던 작업을 찾습니다.',
    examples: [
      '장애가 발생한 순간 해당 GPU에 연결된 Pod는 무엇이었나?',
      '장애 당시 연결된 작업을 확인할 수 있는 사건은 어떤 것인가?',
    ],
    result: '사건의 GPU UUID와 당시 할당 이력이 일치하는 Pod 관계를 제공합니다.',
    inputs: '사건 시각·GPU UUID, 당시 할당·Pod 신원, 영향 확인용 작업 근거가 필요합니다.',
    limit:
      'GPU UUID가 없는 사건은 현재 연결이 제한됩니다. 작업 중단·영향·원인은 확정하지 않으며 현재 매핑을 과거로 소급하지 않습니다.',
    next: '사건 당시 Pod UID와 작업 로그·재시작·중단 기록을 함께 확인하세요.',
    queries:
      '통합 D 설정에서는 DB 사건 스냅샷 + D02 · D06 · D20을 사용합니다. 계산하지 않는 D09·D13 원본 로그는 조회하지 않습니다. 이전 할당 설정은 해당 프로필의 연결 계약을 유지합니다.',
  },
  {
    purpose: '노드에 배치되지 않은 작업의 GPU 요청을 확인합니다.',
    examples: [
      '아직 노드에 배치되지 않은 작업이 요청한 GPU는 얼마나 되나?',
      '배치를 기다리는 작업은 어떤 종류의 GPU 자원을 요청했나?',
    ],
    result: '종료되지 않은 미배치 Pod의 검증된 유효 요청량을 자원 종류별로 표시합니다.',
    inputs:
      'Pod UID·미배치·비종료 상태와 유효 요청량 계약을 갖춘 지표, 자원 카탈로그가 필요합니다.',
    limit:
      'Pending 상태만으로 GPU 부족이라고 판단하지 않습니다. 현재 GPU 부족량·노드 잔여 용량·단편화 원인은 계산하지 않습니다.',
    next: '스케줄러 이벤트, 노드별 자원, affinity·taint 등 배치 제약을 별도로 확인하세요.',
    queries: 'D07 · D12; 유효 요청 계약 effective-v1',
  },
  {
    purpose: 'Namespace별로 어떤 GPU가 연결돼 있었고 얼마나 활동했는지 확인합니다.',
    examples: [
      '각 Namespace에 이 기간 동안 연결됐던 GPU는 몇 대인가?',
      'Namespace별로 활동이 낮아지는 시간대와 지속 저활동 구간은 어디인가?',
    ],
    result:
      '새 기준 1.3에서는 시간대 최대 동시 연결 GPU 수, 같은 모델별 유효 시간 가중 활동률과 GPU별 5% 미만이 30분 이상 이어진 구간을 제공합니다. 연결 시간은 상세 근거에 남습니다.',
    inputs:
      '같은 시각의 GPU–Pod 연결·Pod UID·Namespace·노드·GPU 신원과 활동률이 필요합니다. 할당 이력은 공유 여부 확인에 사용합니다.',
    limit:
      'Namespace의 실제 소비량·독점 할당량·회수 가능량이 아닙니다. 공유/MIG·신원/값 충돌 구간은 평균에서 제외하며, 새 기준은 모델별로 평균을 분리하며 모델을 확인할 수 없는 구간은 제외합니다. 프로젝트별 배분은 이 기본 분석에 포함되지 않습니다.',
    next: 'Namespace만 궁금하면 이 종류만 선택하고, 결과의 적용 집계·유효시간·제외 사유를 확인하세요. Pod 라벨 없는 관측은 유휴로 단정하지 않습니다. 수집 실패·신원 불일치 등 실제 미충족 근거가 있으면 부분 산출로 표시합니다.',
    queries:
      '현재 D 계약: D02 · D06 + D10 · D22. 공유·신원 충돌·누락 구간은 제외합니다. 과거 기준 1.2 결과는 저장된 연결 시간·평균 의미를 유지합니다.',
  },
  {
    purpose: '관측된 GPU의 전력 사용을 에너지로 환산합니다.',
    examples: [
      '이 기간에 관측된 GPU가 사용한 에너지는 몇 kWh인가?',
      '에너지 계산에 실제로 포함된 GPU 관측시간은 얼마나 되나?',
    ],
    result:
      '실제 전력(W)의 유효 관측 구간을 적분해 선택 범위 전체 GPU의 에너지 합계(kWh)를 표시합니다. 클러스터별·Namespace별로 나눈 값은 아닙니다.',
    inputs: '단위가 확인된 실제 GPU 전력의 원본 시각·표본이 필요합니다.',
    limit:
      '전력 제한값(power limit)을 소비 전력으로 쓰지 않습니다. 관측된 GPU·구간의 값이므로 전체 클러스터·시설 전력이나 전기요금으로 해석하지 마세요.',
    next: '빠진 GPU·시간과 전력 지표의 의미를 확인한 뒤 동일 조건끼리 비교하세요.',
    queries: 'D11 · D10',
  },
  {
    purpose: '기록된 조치 전후의 관측 에너지 차이를 확인합니다.',
    examples: [
      '기록한 조치 전후로 같은 GPU들의 에너지 사용량이 얼마나 달라졌나?',
      '비교 기간과 분석 기간에 공통으로 관측된 GPU의 에너지 사용량은 각각 얼마인가?',
    ],
    result:
      '수행됨으로 기록된 조치와 비교 기간이 있으면 두 기간에 공통으로 관측된 GPU의 전후 에너지와 차이를 제공합니다.',
    inputs: '실제 수행 조치 기록 ID, 비교 기간, 분석 기간, 각 기간의 전력 관측이 필요합니다.',
    limit:
      '권고는 수행 조치가 아닙니다. 기간 길이·관측 범위·업무량 차이 때문에 변화가 생길 수 있으므로 인과적 개선 효과나 절감 성과를 확정하지 않습니다.',
    next: '직접 요청에서 ‘조치 기록과 비교 기간 입력’을 켜고 조건을 입력하세요. 조건 없이도 종합·선택 보고서에 포함할 수 있지만 비교 수치 대신 부족 사유를 표시합니다. 자동보고서는 비교 조건을 임의로 만들지 않습니다.',
    queries:
      'DB 조치 기록 + D11 · D02 · D13 · D09; 비교 기간 전력은 별도 수집. 새 소주제별 기준 요청에서 조치 ID 또는 비교 기간이 없으면 O10 전용 조회를 생략합니다. 다른 주제의 동일 조회는 유지합니다.',
  },
  {
    purpose: '수집 상태와 분석에 쓸 수 있었던 관측 범위를 점검합니다.',
    examples: [
      '대상별로 수집 상태가 정상으로 관측된 시간은 얼마나 되나?',
      '이 보고서의 수집 상태와 전체 커버리지를 확인할 근거가 충분한가?',
    ],
    result:
      '새 기준 1.3은 대상별 정상·실패·미관측 시간과 수집 응답시간 평균·최대를 제공합니다. 전체 관측률은 분모가 없으면 산출하지 않습니다.',
    inputs:
      '기간 내 수집 상태 지표가 필요합니다. 전체 커버리지에는 기대 대상 목록과 시간이 추가로 필요합니다.',
    limit:
      '현재 전체 커버리지는 분모 부족으로 산출하지 않습니다. 대상·초 합계는 경과 시간이나 GPU 사용시간이 아닙니다.',
    next: '보고서의 분석 진행 상세에서 query·CPC별 빈 응답·미완료 구간과 사유를 확인하세요. 이 진단은 O11을 선택하지 않아도 기록된 보고서에서 볼 수 있습니다.',
    queries: 'D10 · D22; 전체 커버리지 분모 미구현',
  },
];

const guideSections = [
  ['start', '시작 방법'],
  ['topics', '보고서 종류·분석 내용'],
  ['values', '수치 읽는 법'],
  ['missing', '근거 부족 확인'],
];

export function OperatorGuide() {
  const location = useLocation(),
    navigate = useNavigate();
  const selected = guideSections.find(([key]) => location.hash === `#guide-${key}`)?.[0] ?? 'start';
  const [kindId, setKindId] = useState(reportKinds[0].id);
  const kind = reportKinds.find((item) => item.id === kindId) || reportKinds[0];
  return (
    <div className="page operator-guide">
      <PageHead
        eyebrow=""
        title="운영자 가이드"
        description="GPU 운영 분석의 주제, 필요한 근거와 결과를 읽는 방법입니다."
        actions={
          <Link className="button primary" to="/reports/new">
            보고서 요청
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <Notice>
        현재 코드·개발명세 기준 안내입니다. 실시간 연결 상태나 데이터 보유 여부를 판정하는 화면은
        아닙니다. 실제 보고서의 기간·계산 기준·부족 사유를 함께 확인하세요.
      </Notice>
      <nav className="guide-jump-links" aria-label="가이드 목차">
        {guideSections.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className="button"
            aria-pressed={selected === key}
            aria-controls={`guide-${key}`}
            onClick={() => navigate(`${location.pathname}#guide-${key}`, { replace: true })}
          >
            {label}
          </button>
        ))}
      </nav>
      <section
        id="guide-start"
        hidden={selected !== 'start'}
        className="guide-menu-section"
        aria-label="시작 방법"
      >
        <Panel title="처음에는 이렇게 요청하세요" className="guide-menu-panel">
          <div className="guide-body">
            <ol>
              <li>
                <strong>일일·주간 운영 보고서로 시작하세요.</strong> Namespace 활동과 변화, 기간 내
                사건과 반복 현황을 직전 같은 기간과 비교합니다. 기존 자동 일정과 저장된 보고서는
                이전 계산 기준을 유지합니다. 새 방식은 새 일정을 등록해 사용하세요.
              </li>
              <li>
                <strong>AI 운영 해석에서 대상을 찾고 표·그래프로 근거를 확인하세요.</strong>
                제안은 클러스터·Namespace 이름순으로 묶습니다. 같은 Namespace 안에서는 저장된 제안
                순서를 유지하며, 표에 있는 모든 Namespace에 AI 제안이 생기는 것은 아닙니다. 그래프의
                비교 대상 선택으로 클러스터·Namespace·GPU 모델별 시간대 관측을 확인합니다. 빈 구간은
                0%가 아닙니다. 활동률은 연결 GPU의 관측 표본 평균이며, 독점 사용량이나 회수 가능한
                GPU를 뜻하지 않습니다. 사건 현황에서는 알림 상태, RCA 조사, 실제 복구를 구분합니다.
              </li>
              <li>
                <strong>관측 범위와 분석 날짜를 확인하세요.</strong> 보고서 제목의 날짜는 작성일이
                아닌 분석 대상일입니다. 예를 들어 23일에 만든 22일 보고서는 ‘2026년 10월 22일 GPU
                클러스터 운영 분석 보고서’로 표시합니다. 주간 보고서는 분석한 날짜 범위를
                표시합니다. 수집·집계 주제 수와 운영 제안 유형 수는 다르므로 제목에 개수를 붙이지
                않습니다. CPC는 클러스터입니다. 전체 클러스터 또는 필요한 클러스터·Namespace를
                선택하세요. 모든 표시 시각은 한국 시간 기준이며 요청 접수 시각·분석 대상 기간·보고서
                실행시간은 서로 다릅니다. 기간 밖의 LLM 추론 부하는 해당 보고서 수치에 포함되지
                않습니다.
              </li>
              <li>
                <strong>일일 또는 주간과 마지막 분석 날짜를 정합니다.</strong>
                일일은 하루, 주간은 마지막 날짜까지 7일입니다. 직전 같은 길이의 기간과 비교합니다.
              </li>
              <li>
                <strong>접수 후 실행 상태와 결과 품질을 따로 확인하세요.</strong> 작업 이력의 종류는
                ‘운영 분석 보고서’로 표시합니다. ‘직접 요청’은 운영자가 요청한 보고서, ‘자동 생성’은
                등록한 일정으로 만들어진 보고서입니다. 실행 완료여도 결과가 부분 산출·근거 부족일 수
                있으므로 소주제별 이유를 확인하세요.
              </li>
            </ol>
            <section className="guide-reading-group">
              <h3>반복 보고서와 긴 기간 요청</h3>
              <p>
                <strong>반복 보고서는 자동 보고서 설정에서 등록하세요.</strong> 일일·주간 중 고르며
                직전 완료된 달력 기간을 분석합니다. 월간은 기존 방식의 일정에서만 유지됩니다.
              </p>
              <p>
                긴 기간도 요청할 수 있지만 적용된 기간·조회·시간 한도와 데이터 양에 따라 일부 수집이
                끝나지 않을 수 있습니다.
              </p>
            </section>
            <Link className="text-link" to="/reports">
              보고서 이력으로 이동
            </Link>
          </div>
        </Panel>
      </section>
      <section
        id="guide-topics"
        hidden={selected !== 'topics'}
        className="guide-menu-section"
        aria-label="보고서 종류·분석 내용"
      >
        <Panel
          title="궁금한 보고서 종류를 고르세요"
          description="종류를 선택하면 해당 설명과 포함된 분석만 표시합니다."
          className="guide-menu-panel"
        >
          <div className="guide-menu-body">
            <label className="guide-kind-select">
              <span>설명할 보고서 종류</span>
              <select value={kindId} onChange={(event) => setKindId(event.target.value)}>
                {reportKinds.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="guide-kind-layout">
              <div className="guide-kind-picker" role="group" aria-label="설명할 보고서 종류">
                {reportKinds.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="button"
                    aria-pressed={kind.id === item.id}
                    aria-controls="guide-kind-content"
                    onClick={() => setKindId(item.id)}
                  >
                    <strong>{item.id === 'health' ? 'GPU 상태·에너지·장애' : item.name}</strong>
                  </button>
                ))}
              </div>
              <section id="guide-kind-content" aria-labelledby="guide-kind-title" key={kind.id}>
                <div className="guide-kind-panel">
                  <header className="guide-kind-header">
                    <div>
                      <h3 id="guide-kind-title">{kind.name}</h3>
                      <p>{kind.description}</p>
                    </div>
                    <Link className="button primary" to={`/reports/new?kind=${kind.id}`}>
                      이 종류로 보고서 만들기
                    </Link>
                  </header>
                  <table className="guide-kind-table" aria-label={`${kind.name} 안내`}>
                    <tbody>
                      <tr>
                        <th scope="row">이런 판단에 도움</th>
                        <td>{kind.insight}</td>
                      </tr>
                      <tr>
                        <th scope="row">필요한 자료</th>
                        <td>{kind.requirement}</td>
                      </tr>
                      <tr>
                        <th scope="row">해석할 때 주의</th>
                        <td>{kind.limit}</td>
                      </tr>
                      <tr>
                        <td colSpan={2} className="guide-kind-analyses">
                          <h4>포함된 세부 분석 · {kind.topicIds.length}개</h4>
                          <p>
                            질문 예시를 보고, 펼치면 계산 기준과 필요한 자료를 확인할 수 있습니다.
                          </p>
                          {topics.map((name, i) => {
                            if (!kind.topicIds.includes(topicId(i))) return null;
                            const guide = topicGuides[i];
                            return (
                              <details key={topicId(i)} className="guide-topic">
                                <summary>
                                  <span className="guide-topic-id">{topicId(i)}</span>
                                  <span>
                                    <strong>{name}</strong>
                                    <span className="guide-topic-purpose">{guide.purpose}</span>
                                    <span className="guide-topic-examples">
                                      <span className="guide-topic-examples-label">
                                        이런 게 궁금할 때 선택하세요
                                      </span>
                                      {guide.examples.map((question) => (
                                        <span key={question}>• {question}</span>
                                      ))}
                                    </span>
                                  </span>
                                </summary>
                                <dl className="guide-topic-fields">
                                  <dt>표시 기준</dt>
                                  <dd>{topicDisplayBases[topicId(i)]}</dd>
                                  <dt>현재 나오는 결과</dt>
                                  <dd>{guide.result}</dd>
                                  <dt>필요한 데이터</dt>
                                  <dd>{guide.inputs}</dd>
                                  <dt>해석할 때 주의</dt>
                                  <dd>{guide.limit}</dd>
                                  <dt>운영자가 확인할 것</dt>
                                  <dd>{guide.next}</dd>
                                </dl>
                                <details className="guide-technical">
                                  <summary>개발·수집 기준 확인</summary>
                                  <p>{guide.queries}</p>
                                </details>
                              </details>
                            );
                          })}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <Notice>
              이 목록은 이전 주제별 분석의 설명입니다. 새 기본 보고서는 Namespace 활동과 변화,
              사건과 반복 현황으로 구성합니다. 기존 주제는 보고서 만들기의 ‘이전 분석 방식’에서
              선택할 수 있습니다. 전체 선택이 수집량 감소를 뜻하지는 않으며, 자료가 부족한 소주제도
              이유와 함께 남습니다.
            </Notice>
          </div>
        </Panel>
      </section>
      <section
        id="guide-values"
        hidden={selected !== 'values'}
        className="guide-menu-section"
        aria-label="수치 읽는 법"
      >
        <Panel title="수치를 이렇게 읽으세요" className="guide-menu-panel">
          <div className="guide-body">
            <section className="guide-reading-group">
              <h3>숫자와 단위</h3>
              <table className="guide-kind-table guide-values-table" aria-label="숫자와 단위">
                <tbody>
                  <tr>
                    <th scope="row">0% / 산출 불가 / 미계산</th>
                    <td>
                      0%는 유효한 관측으로 계산된 값입니다. 아주 작은 값은 표시 자릿수에서 반올림될
                      수 있습니다. 산출 불가는 필요한 데이터·조건을 충족하지 못한 값(null), 미계산은
                      저장 결과에 해당 지표가 없는 경우입니다. 모델이 메모리에 올라와 있거나 Pod가
                      Running이어도 분석 기간의 활동률은 0%일 수 있습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">연결 GPU 평균 활동률</th>
                    <td>
                      새 일일·주간 집계 보고서는 유효한 활동률 표본의 합계를 표본 수로 나눈
                      평균입니다. 기존 O08 기준 1.3의 시간 가중 평균과 구분하세요. 짧은 부하는
                      평균에서 작게 보일 수 있으며 Namespace의 독점 사용량이나 실제 연산 소비 비율을
                      뜻하지 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">연결 GPU 수</th>
                    <td>
                      기간 중 한 번이라도 연결이 확인된 고유 GPU 대수입니다. 동시에 사용한 최대
                      대수가 아닙니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">GPU·시간</th>
                    <td>
                      GPU별 시간을 누적한 단위입니다. 예를 들어 GPU 4대가 2시간 연결됐다면 8
                      GPU·시간입니다. 2시간 보고서에서 약 8 GPU·시간이 나와도 기간 오류는 아닙니다.
                      관측 공백·제외 구간으로 값이 줄 수 있고, 공유 GPU는 Namespace 사이에 중복될 수
                      있습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">소주제별 표시 기준</th>
                    <td>
                      한 보고서 안에서도 기준이 다릅니다. Namespace 현황은 클러스터·Namespace별,
                      메모리·온도는 GPU 장비별, 에너지는 선택 범위 전체 GPU의 합계입니다. 모든
                      수치를 Namespace별 사용량으로 읽거나 서로 다른 단위끼리 더하지 마세요.
                    </td>
                  </tr>
                </tbody>
              </table>
            </section>
            <section className="guide-reading-group">
              <h3>실행 상태와 결과 품질</h3>
              <table
                className="guide-kind-table guide-values-table"
                aria-label="실행 상태와 결과 품질"
              >
                <tbody>
                  <tr>
                    <th scope="row">실행 상태</th>
                    <td>
                      실행 대기·실행 중·재시도 대기·실행 완료는 작업의 진행 상태입니다. 실행
                      실패·기한 만료는 상세 화면에서 종료 사유를 확인하세요. 실행 완료가 모든 분석의
                      성공을 뜻하지는 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">결과 품질</th>
                    <td>
                      산출 가능은 해당 계산의 근거가 충족됐다는 뜻이며 장비가 정상이라는 판정은
                      아닙니다. 부분 산출은 일부 값이나 판단에 제한이 있고, 근거 부족은 계산에
                      필요한 자료·조건이 부족한 상태입니다. 미발행은 아직 공개 결과가 없다는
                      뜻입니다. 예를 들어 ‘실행 완료’와 ‘부분 산출’이 함께 나올 수 있습니다. 자료가
                      없다는 사실을 정상 또는 0으로 바꾸지 않습니다.
                    </td>
                  </tr>
                </tbody>
              </table>
            </section>
            <section className="guide-reading-group">
              <h3>AI 해석과 권고</h3>
              <p>
                AI 운영 해석은 클러스터별 카드로 나누고 카드 안에서 네임스페이스별로 묶습니다.
                제목은 ‘AI 운영 해석’이며, 바로 아래에 대상 클러스터 : <code>cpc-1</code>처럼 분석
                대상을 표시합니다. 네임스페이스 : <code>프로젝트 이름</code>은 라벨·콜론·값의 열을
                맞추고 아래 제안에 붙여 표시합니다. 소제목은 배지 대신 색이 있는 글자로 본문과 이어
                표시합니다. 소제목 다음에 AI 제안 본문을 읽고, 그 아래에서 관측 시간과 GPU 모델을
                확인합니다. 일반적인 유형 설명은 ‘판단 근거와 적용 조건’을 펼치면 볼 수 있습니다.
                과거 관측이며 반복성과 실행 조건 확인이 필요하다는 안내는 본문 아래에 짧게 남깁니다.
                자세한 조건은 상세 근거로 모읍니다. 클러스터와 네임스페이스는 이름순이며 같은
                네임스페이스 안에서는 저장된 제안 순서입니다. 네임스페이스 사이는 구분선으로, 같은
                네임스페이스의 제안 사이는 간격으로 나눕니다. 소제목·본문·시간·상세 근거의 시작선을
                맞추고 작은 화면에서는 추가 들여쓰기를 없앱니다. 표시 순서는 심각도나 실행
                우선순위를 뜻하지 않습니다.
              </p>
              <table className="guide-kind-table guide-values-table" aria-label="AI 해석과 권고">
                <tbody>
                  <tr>
                    <th scope="row">해석과 실행의 구분</th>
                    <td>
                      코드가 수치를 계산하고 근거 후보를 선별하면, AI가 그 근거 안에서 관측한 현상과
                      운영 선택·확인할 사항을 설명합니다. AI 응답이 검증을 통과하지 못하면 계산
                      요약을 표시합니다. 실행 완료와 AI 해석 채택은 구분하며, 제안은 조치 승인이나
                      수행 완료가 아닙니다. GPU 회수·설정 변경은 자동 실행하지 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">관측 구간과 비교 구간</th>
                    <td>
                      관측 구간은 해당 현상이 확인된 시간 범위입니다. 비교형 제안에만 비교 구간과
                      낮은 활동 구간이 함께 나옵니다. 여러 구간형은 각각 따로 표시합니다. 모든
                      구간은 KST이며 끝 시각은 포함하지 않습니다. 시간 범위를 확인할 수 없으면
                      미확인으로 남깁니다. 이미 지난 시간대는 앞으로의 사용 가능한 GPU를 보장하지
                      않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">화면과 HTML</th>
                    <td>
                      ‘판단 근거와 적용 조건’을 열면 해당 제안의 근거와 한계를 확인할 수 있습니다.
                      운영 콘솔의 현재 화면 HTML 저장과 서버 HTML 다운로드도 같은 정렬·대상·시간
                      표시를 사용합니다. 저장된 AI 원문과 수치·근거는 바꾸지 않으며 조회·내보내기는
                      AI를 다시 호출하지 않습니다.
                    </td>
                  </tr>
                </tbody>
              </table>
              <h3>운영 제안의 소제목은 이렇게 읽으세요</h3>
              <p>
                아래 유형 중 근거가 있어 선별된 제안만 보고서에 표시됩니다. 소제목의 색은 제안
                종류를 구분하며 심각도나 실행 우선순위를 뜻하지 않습니다.
              </p>
              <table className="guide-kind-table guide-values-table" aria-label="운영 제안 유형">
                <tbody>
                  {adviceGuides.map(([kind, meaning]) => (
                    <tr key={kind}>
                      <th scope="row">
                        <span className="advice-kind" data-kind={kind}>
                          {advicePresentation({ kind }).title}
                        </span>
                      </th>
                      <td>{meaning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </Panel>
      </section>
      <section
        id="guide-missing"
        hidden={selected !== 'missing'}
        className="guide-menu-section"
        aria-label="근거 부족 확인"
      >
        <Panel title="근거 부족이면 무엇부터 확인하나요?" className="guide-menu-panel">
          <div className="guide-body">
            <p>
              보고서 본문의 <strong>분석 진행 상세</strong>를 펼쳐 해당 주제의 부족 사유와
              query·CPC별 수집 구간을 확인하세요. 근거 부족만으로 연결 장애를 단정할 수 없습니다.
            </p>
            <div className="table-wrap">
              <table className="guide-help-table">
                <thead>
                  <tr>
                    <th>확인한 상태</th>
                    <th>뜻과 다음 확인</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">조회 오류·연결 실패</th>
                    <td>기록된 오류 코드와 대상 데이터 소스·접속 설정을 확인합니다.</td>
                  </tr>
                  <tr>
                    <th scope="row">빈 응답</th>
                    <td>
                      <p>조회는 끝났지만 조건에 맞는 표본이 없었습니다.</p>
                      <p>기간·Namespace·지표 이름과 보존 기간을 대조합니다.</p>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">조회 한도·시간 소진</th>
                    <td>
                      <p>계획 중단 또는 일부 구간 미완료입니다.</p>
                      <p>
                        저장된 적용 한도·실제 호출 수·미완료 기간을 확인합니다. 연결 실패와 구분하고
                        범위를 줄이거나 운영 설정을 점검합니다.
                      </p>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">할당 이력·신원·활동 부족</th>
                    <td>
                      <p>필요한 지표, 동일 시각의 GPU–Pod UID 연결, 활동률 단위를 확인합니다.</p>
                      <p>연결 관측이 있어도 독점 할당 근거는 없을 수 있습니다.</p>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">조치 기록·비교 기간 미지정</th>
                    <td>
                      <p>조치 전후 비교의 입력 조건이 없는 상태이며 연결 장애가 아닙니다.</p>
                      <p>
                        직접 요청에서 수행한 조치 ID와 비교 기간을 입력하세요. 자동보고서는 이
                        조건을 임의로 만들지 않고 부족 사유를 남기며 다른 소주제 분석을 계속합니다.
                      </p>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">공유·모델 혼합·값 충돌</th>
                    <td>
                      <p>관측은 있지만 귀속이나 평균 비교 조건이 맞지 않습니다.</p>
                      <p>제외 사유와 유효시간을 확인하며 억지로 평균을 채우지 않습니다.</p>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">현재 미지원·미구현</th>
                    <td>
                      <p>선택한 주제·집계와 위 주제별 제한을 확인합니다.</p>
                      <p>데이터나 연결을 복구해도 아직 구현하지 않은 분석이 생기지는 않습니다.</p>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="muted">
              수집 응답 완료는 표본이 연속적이거나 계산·권고가 가능하다는 뜻이 아닙니다. 구 보고서에
              수집 진단이 없으면 조회 여부를 추정하지 않습니다.
            </p>
          </div>
        </Panel>
      </section>
      <details className="guide-sources">
        <summary>안내 기준과 적용 범위</summary>
        <p>
          일일·주간 집계 보고서는 Ops 집계 명세의 수치·해석 범위와 화면·HTML 표시 규칙을 따릅니다.
          기존 보고서 종류는 생성 당시의 계산 기준을 유지하므로 새 집계 보고서와 구분해 읽으세요. 이
          안내는 모든 대상에 제안이 생기거나 AI가 자유롭게 원인을 확정한다는 뜻이 아닙니다. 실제
          보고서에 기록된 계산 기준·분석 기간·자료 상태를 함께 확인하세요.
        </p>
        <ul>
          <li>docs/specs/ops-agent/aggregate-report-v1.md</li>
          <li>docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md</li>
          <li>docs/specs/common/04_Agent_동작_판단_명세서.md</li>
          <li>
            ops-agent/src/ops_agent/workflow.py · namespace_usage.py · collection.py · report.py
          </li>
          <li>ops-agent/src/ops_agent/namespace_advice.py · report_interpretation.py</li>
          <li>shared/python/src/agent_common/calculations.py</li>
        </ul>
      </details>
    </div>
  );
}
