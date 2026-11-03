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
    '스케줄러 사유·GPU 요청·실제 할당과 부서·프로젝트 한도를 대조합니다. 부족이 확인된 경우에만 추가 할당을 검토하며 수량은 제안하지 않습니다.',
  ],
  [
    'repeated_activity',
    '각 관측 구간의 GPU 요청·할당과 스케줄러 기록을 확인합니다. 떨어진 구간 사이까지 계속 혼잡했거나 매일 반복됐다고 보지 않습니다.',
  ],
  [
    'schedule_candidate',
    '같은 네임스페이스에서 시작 시각을 바꿀 수 있는 작업의 마감·예약·가용 GPU·메모리 요구를 확인합니다. 이후에도 같은 패턴인지 확인한 뒤 일부 작업만 시험합니다.',
  ],
  [
    'relative_activity',
    '비교 구간에 실행했던 작업 중 시작 시각을 바꿀 수 있는 일부를 대상으로 합니다. 같은 네임스페이스 안에서 향후 시간을 나눠볼 시험이며 다른 네임스페이스로 옮기는 제안이 아닙니다.',
  ],
  [
    'queue_review',
    '노드 배정 전이라면 스케줄러 기록을, 배정 뒤라면 Pod 상태·이벤트를 확인합니다. 같은 구간의 근거가 부족하면 어느 단계인지부터 확인합니다.',
  ],
  [
    'resident_memory',
    '연결된 Pod·Job과 확인된 작업 유형 라벨을 살펴봅니다. 계속 실행해야 하는 작업인지, 새 작업의 메모리 요구를 수용할 수 있는지 별도로 판단합니다.',
  ],
  [
    'batch_progress',
    '대기가 남아 있다면 먼저 실행이 막힌 단계를 확인합니다. 완료 기록은 같은 유형·조건의 작업인지 대조한 뒤 참고하며, 완료 때문에 대기가 줄었다고 단정하지 않습니다.',
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
  ['start', '읽는 순서·요청'],
  ['topics', '현재 보고서 구성'],
  ['advice', '운영 제안 7가지'],
  ['values', '수치 읽는 법'],
  ['missing', '누락·AI 미채택'],
  ['legacy', '이전 분석 방식'],
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
        description="운영 보고서에서 무엇을 판단하고, 어떤 근거를 확인할지 안내합니다."
        actions={
          <Link className="button primary" to="/reports/new">
            보고서 요청
          </Link>
        }
      />
      <NavTabs items={reportTabs} />
      <Notice>
        저장된 보고서를 읽는 방법입니다. 실시간 연결 상태나 데이터 보유 여부를 판정하는 화면은
        아닙니다. 보고서마다 생성 당시의 기준·자료·AI 채택 상태가 다를 수 있습니다.
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
        aria-label="읽는 순서·요청"
      >
        <Panel title="보고서를 읽는 순서" className="guide-menu-panel">
          <div className="guide-body">
            <ol>
              <li>
                <strong>분석한 날짜와 대상을 먼저 확인하세요.</strong>
                제목의 날짜는 작성일이 아닌 분석 대상일입니다. 클러스터(CPC)와 네임스페이스
                (Namespace)를 확인하세요. 보고기간은 KST 기준이며 끝 시각은 포함하지 않습니다.
              </li>
              <li>
                <strong>실행 완료와 AI 해석 채택을 구분하세요.</strong>
                보고서가 발행돼도 자료는 부분 산출일 수 있습니다. 주제별로 AI 운영 해석인지 계산
                결과 요약인지 확인하고, 누락된 값은 0이나 정상으로 읽지 마세요.
              </li>
              <li>
                <strong>소제목 → 제안 기준 → 본문 → 근거 순서로 읽으세요.</strong>
                소제목은 검토할 운영 선택입니다. ‘제안 기준’은 종류별 일반 안내이며 AI가 새로 작성한
                문장이 아닙니다. 본문을 읽은 뒤 ‘판단 근거와 적용 조건’에서 실제 관측과 판단 한계를
                확인하세요.
              </li>
              <li>
                <strong>표·그래프로 대조하고 실행 여부는 별도로 결정하세요.</strong>
                제안은 클러스터·네임스페이스 이름순이며, 같은 대상 안에서는 저장된 순서입니다.
                심각도 순위가 아닙니다. 신규 콘솔2에서는 제안에서 대상·구간 그래프로 이동할 수
                있습니다. 실제 수행한 조치만 검토·조치 기록에 남기세요.
              </li>
            </ol>
            <section className="guide-reading-group">
              <h3>일일 운영 보고서로 시작하세요</h3>
              <p>
                직접 요청은 분석할 날짜와 대상을 정합니다. 해당 하루를 분석하고 직전 하루와
                비교합니다. 신규 주간 보고서 요청은 현재 화면에서 제공하지 않습니다.
              </p>
              <p>
                자동 보고서는 일일 일정을 등록하며 직전 완료된 하루를 분석합니다. 기존 주간 일정은
                자동으로 중지되지 않습니다. 실행을 원하지 않으면 일정 상세에서 일시 정지하세요.
                저장된 주간 보고서 조회·다운로드와 기존 일정 관리는 유지됩니다. 신규 기본 보고서는
                임의 기간·월간 요청을 지원하지 않습니다.
              </p>
              <p>
                ‘직접 요청’과 ‘자동 생성’은 생성 방식의 구분입니다. 화면을 다시 열거나 내려받아도
                과거 결과에 최신 해석 기준을 다시 적용하지 않습니다.
              </p>
              <Link className="text-link" to="/reports">
                보고서 이력으로 이동
              </Link>
            </section>
          </div>
        </Panel>
      </section>
      <section
        id="guide-topics"
        hidden={selected !== 'topics'}
        className="guide-menu-section"
        aria-label="현재 보고서 구성"
      >
        <Panel
          title="현재 보고서는 두 부분으로 읽습니다"
          description="수집·집계 주제 2개와 네임스페이스 운영 제안 7가지는 서로 다른 분류입니다."
          className="guide-menu-panel"
        >
          <div className="guide-body">
            <section className="guide-reading-group">
              <h3>Namespace별 GPU 활동 현황</h3>
              <p>
                클러스터·네임스페이스·GPU 모델별 활동률과 메모리, GPU 요청 작업의 대기·완료 기록을
                봅니다. 확인된 작업 유형·GPU 요청·노드 배정 자료가 있으면 같은 대상과 관측 구간에
                연결해 해석합니다.
              </p>
              <p>
                <strong>도움이 되는 판단:</strong> 대기가 생긴 단계 점검, 조건부 추가 할당 검토,
                향후 시작 시간 조정 시험, 메모리 점유 확인, 완료 기록 활용입니다. 표의 모든
                네임스페이스에 제안이 생기지는 않습니다.
              </p>
              <p>
                <strong>판단 한계:</strong> 활동률은 연결 GPU의 관측입니다. 독점 사용량이나 빈 GPU
                수가 아니며, GPU 추가 수량·대기 원인·다음날 실행 가능성을 보장하지 않습니다.
              </p>
            </section>
            <section className="guide-reading-group">
              <h3>기간 내 장애 알림 현황</h3>
              <p>
                기간 내 저장된 사건 수와 직전 기간의 차이, 장애 종류·발생 대상과 공개된 RCA를
                확인합니다. 장비·증상 식별이 확인된 반복과 식별 부족으로 판단하지 못한 사건을
                구분합니다.
              </p>
              <p>
                <strong>도움이 되는 판단:</strong> 어떤 장비·알림의 기존 조사와 점검 기록을 먼저
                볼지 정합니다. 이 부분은 사건·장비 기준이며 네임스페이스로만 한정되지 않습니다.
              </p>
              <p>
                <strong>판단 한계:</strong> 비슷한 알림만으로 같은 원인이나 실제 복구를 확정하지
                않습니다. 운영보고서를 요청해도 새 RCA 조사가 실행되지는 않습니다.
              </p>
            </section>
            <section className="guide-reading-group">
              <h3>자료에서 제안이 만들어지는 과정</h3>
              <ol>
                <li>
                  요청한 기간·대상의 저장 지표와 사건을 읽고, 코드가 연결 관계·수치·자료 상태를
                  확인합니다.
                </li>
                <li>기준을 만족하는 관측 구간에서 운영 제안 후보를 만들고 일부를 선별합니다.</li>
                <li>
                  현재 네임스페이스 해석은 AI가 관측·이유 한 문장을 쓰고, 코드가 점검 목적·행동과
                  수치 근거를 붙입니다. 사건 해석은 별도 작성 규칙을 따릅니다.
                </li>
                <li>
                  응답을 검증하고 필요한 경우 한 번 보완합니다. 통과한 주제는 보존하고 실패한 주제는
                  계산 요약으로 남깁니다.
                </li>
              </ol>
              <p>
                보고서 조회는 저장된 결과를 보여줄 뿐, 새 LLM 요청이나 집계를 실행하지 않습니다.
              </p>
            </section>
          </div>
        </Panel>
      </section>
      <section
        id="guide-advice"
        hidden={selected !== 'advice'}
        className="guide-menu-section"
        aria-label="운영 제안 7가지"
      >
        <Panel
          title="각 제안에서 무엇을 판단하나요?"
          description="선별된 대상·관측 구간의 조건부 제안입니다. 색은 종류를 구분하며 심각도나 실행 우선순위가 아닙니다."
          className="guide-menu-panel"
        >
          <div className="guide-body">
            <p>
              각 제안은 표시된 클러스터의 해당 네임스페이스에 관한 것입니다. 아래 설명은 일반
              기준이며 실제 관측은 보고서 본문과 근거에서 확인하세요.
            </p>
            <table className="guide-kind-table guide-values-table" aria-label="운영 제안 유형">
              <tbody>
                {adviceGuides.map(([kind, next]) => (
                  <tr key={kind}>
                    <th scope="row">
                      <span className="advice-kind" data-kind={kind}>
                        {advicePresentation({ kind }).title}
                      </span>
                    </th>
                    <td>
                      <p>
                        <strong>제안 기준</strong> {advicePresentation({ kind }).basis}
                      </p>
                      <p>
                        <strong>다음 확인</strong> {next}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <section className="guide-reading-group">
              <h3>어떤 제안에만 비교 시간이 나오는 이유</h3>
              <p>
                ‘작업 시작 시간을 나눠볼지 검토’는 같은 날의 비교 구간과 낮은 활동 구간을 함께
                봅니다. ‘작업 시작 시간을 바꿔볼지 검토’는 정해둔 낮은 활동 기준을 만족한 구간만
                보여줍니다. 반복 관측은 떨어진 구간을 각각 표시하고, 나머지는 해당 관측 구간을
                표시합니다. KST이며 끝 시각은 포함하지 않습니다.
              </p>
              <p>
                이미 지난 시간으로 작업을 옮기라는 뜻이 아닙니다. 이후에도 같은 시간대의 활동이
                낮은지, 실제 사용할 GPU와 작업 조건이 맞는지 확인한 뒤 일부 작업을 시험할
                후보입니다.
              </p>
            </section>
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
                      0%는 유효한 관측으로 계산된 값이며 미사용 확정이 아닙니다. 아주 작은 값은 표시
                      자릿수에서 반올림될 수 있습니다. 산출 불가는 필요한 데이터·조건을 충족하지
                      못한 값(null), 미계산은 저장 결과에 해당 지표가 없는 경우입니다. 모델이
                      메모리에 올라와 있거나 Pod가 Running이어도 분석 기간의 활동률은 0%일 수
                      있습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">연결 GPU 평균 활동률</th>
                    <td>
                      집계 보고서는 유효한 활동률 표본의 합계를 표본 수로 나눈 평균입니다. 기존 O08
                      기준 1.3의 시간 가중 평균과 구분하세요. 짧은 부하는 평균에서 작게 보일 수
                      있으며 Namespace의 독점 사용량이나 실제 연산 소비 비율을 뜻하지 않습니다.
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
                    <th scope="row">GPU 메모리 사용 비율</th>
                    <td>
                      사용량 ÷ (사용량 + 여유량) × 100입니다. 연결된 GPU 장치의 관측값이며
                      네임스페이스의 전용 사용량이 아닙니다. 활동률과 메모리는 유효한 관측 구간이
                      서로 다를 수 있고, 메모리 여유가 새 작업의 배치 가능성을 보장하지 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">대기·미배치 Pod</th>
                    <td>
                      GPU를 요청한 일반 컨테이너가 있는 Pod의 보조 관측입니다. 대기는 Pending 상태,
                      미배치는 아직 노드가 배정되지 않은 상태를 봅니다. 시간대별 최대값이며 각
                      최대값의 시각은 다를 수 있습니다. 대기 수만으로 GPU 부족이나 대기 시간을
                      계산하지 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">완료 Job·경과시간</th>
                    <td>
                      보고기간에 성공 완료가 확인된 Job 표본입니다. 기간 전에 시작된 작업도 포함될
                      수 있습니다. 시작부터 완료까지의 경과시간은 대기·준비를 포함하며, 순수 GPU
                      연산 시간이나 다음 작업의 예상 소요시간이 아닙니다.
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
                    <th scope="row">서로 다른 집계 기준</th>
                    <td>
                      현재 기본 보고서의 활동·메모리·작업 관측과 이전 분석 방식의 할당 시간·에너지는
                      서로 다른 값입니다. 저장된 단위와 계산 기준을 확인하고 다른 단위끼리 더하지
                      마세요.
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
          </div>
        </Panel>
      </section>
      <section
        id="guide-missing"
        hidden={selected !== 'missing'}
        className="guide-menu-section"
        aria-label="누락·AI 미채택"
      >
        <Panel
          title="자료가 없거나 AI 해석이 보이지 않을 때"
          description="수집, 계산, AI 작성·검증, 발행은 서로 다른 단계입니다. 저장된 사유가 있는 범위에서 구분하세요."
          className="guide-menu-panel"
        >
          <div className="guide-body">
            <p>
              본문의 ‘집계 기준과 근거’, ‘세부 수치와 자료 상태’를 먼저 확인하세요. 화면에 따라
              ‘분석 진행 상세’ 또는 개발 콘솔의 작업 진단에서 더 자세한 실패 기록을 볼 수 있습니다.
              과거 결과에 없는 사유는 추정하지 않습니다.
            </p>
            <table className="guide-help-table" aria-label="누락과 AI 미채택 확인">
              <thead>
                <tr>
                  <th>보이는 상태</th>
                  <th>뜻과 다음 확인</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">AI 운영 해석</th>
                  <td>
                    해당 주제의 설명이 검증을 통과했습니다. 자료가 완전하거나 운영 조치가 승인됐다는
                    뜻은 아닙니다.
                  </td>
                </tr>
                <tr>
                  <th scope="row">일부 주제만 AI 해석</th>
                  <td>
                    통과한 주제는 AI 해석을 남기고 실패한 주제는 계산 요약을 표시합니다. 보고서
                    전체를 AI 성공 또는 실패로 묶지 마세요.
                  </td>
                </tr>
                <tr>
                  <th scope="row">계산 결과 요약</th>
                  <td>
                    AI 응답을 채택하지 못했거나 호출하지 못한 결과일 수 있습니다. 저장된 작성
                    방식·실패 사유를 확인하세요. 수치까지 없다는 뜻은 아닙니다.
                  </td>
                </tr>
                <tr>
                  <th scope="row">특정 네임스페이스의 제안 없음</th>
                  <td>
                    관측이 있어도 후보 조건이나 선별 범위에 들지 않을 수 있습니다. 먼저 비교표와
                    시간대 그래프의 자료 상태를 확인하세요. 제안이 없다는 사실만으로
                    정상·미사용·수집 실패를 판단하지 않습니다.
                  </td>
                </tr>
                <tr>
                  <th scope="row">빈 응답·조회 오류</th>
                  <td>
                    빈 응답은 조건에 맞는 표본이 없는 경우이고 오류는 조회를 마치지 못한 경우입니다.
                    기간·대상·지표·보존 기간과 저장된 오류를 각각 대조합니다.
                  </td>
                </tr>
                <tr>
                  <th scope="row">일부 시간·작업 자료 제외</th>
                  <td>
                    동일 시각의 GPU–Pod 연결, Pod·Job 신원, 중복·시간 겹침, 표본 부족 등 기록된 제외
                    사유를 확인합니다. 원본이 존재해도 계산 조건을 충족하지 못할 수 있으며 공백을
                    0으로 채우지 않습니다.
                  </td>
                </tr>
                <tr>
                  <th scope="row">미발행·실행 실패</th>
                  <td>
                    아직 공개 결과가 없는 상태입니다. 작업 이력의 진행 단계·종료 사유를 확인하세요.
                    발행된 계산 요약과 구분합니다.
                  </td>
                </tr>
              </tbody>
            </table>
            <section className="guide-reading-group">
              <h3>‘예산 소진’은 어느 단계인지 먼저 확인하세요</h3>
              <table className="guide-kind-table guide-values-table" aria-label="예산과 한도 구분">
                <tbody>
                  <tr>
                    <th scope="row">자료 조회 한도</th>
                    <td>
                      호출 수·시간·응답 크기 한도 때문에 일부 조회나 연결 검증이 끝나지 않을 수
                      있습니다. 미완료 대상·기간과 실제 호출 기록을 확인합니다. LLM 토큰을 늘려도
                      빠진 관측이 채워지지 않습니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">LLM 입력·출력·시간 한도</th>
                    <td>
                      입력이 너무 크거나 응답이 잘리거나 호출 시간이 끝나면 AI 채택에 영향을 줍니다.
                      미호출·응답 실패·보완 실패를 구분하고, 한도를 늘리기 전에 저장된 종료 사유를
                      확인합니다.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">이유문 길이·내용 검증</th>
                    <td>
                      현행 네임스페이스 해석은 AI 이유문에 최대 100자를 허용하고 코드 행동·근거를
                      포함한 전체 길이는 따로 계산합니다. 토큰 예산과 다른 규칙입니다.
                      참조·사실·판단 한계 검사는 그대로이며, 한도를 늘려도 내용 오류가 해결되지는
                      않습니다. 과거 보고서는 생성 당시 기준을 따릅니다.
                    </td>
                  </tr>
                </tbody>
              </table>
              <p>
                한도 조정은 새 실행의 조건을 바꾸는 작업입니다. 이 가이드는 운영 설정을 변경하거나
                실패한 보고서를 자동으로 재실행하지 않습니다.
              </p>
            </section>
          </div>
        </Panel>
      </section>
      <section
        id="guide-legacy"
        hidden={selected !== 'legacy'}
        className="guide-menu-section"
        aria-label="이전 분석 방식"
      >
        <Panel
          title="이전 분석 방식 · O01~O11"
          description="기존 보고서와 일정의 결과를 읽을 때 참고하세요. 현재 기본 보고서와 계산 기준이 다릅니다."
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
              이전 분석 방식은 보고서 만들기에서 별도로 선택할 수 있습니다. 전체 선택이 수집량
              감소를 뜻하지는 않으며, 자료가 부족한 분석도 이유와 함께 남습니다.
            </Notice>
          </div>
        </Panel>
      </section>
      <details className="guide-sources">
        <summary>안내 기준과 적용 범위</summary>
        <p>
          현재 집계 경로와 이 프런트엔드의 표시 기준입니다. 과거 보고서는 저장된 AI 원문·수치·품질
          상태를 유지하며 새로운 필드나 해석을 덧붙이지 않습니다. ‘현재 화면 HTML 저장’은 화면
          기준이며, 서버 HTML 다운로드도 저장 결과에 같은 소제목·제안 기준을 붙여 보여줍니다. CSV는
          저장된 수치를 내보냅니다. 조회·내보내기는 AI를 다시 호출하지 않습니다.
        </p>
        <p>
          이 안내는 실제 운영 배포나 최신 보고서의 품질을 확인한 결과가 아닙니다. 네임스페이스
          이유문 길이 설명은 ops-interpretation-reason-budget-v16 기준입니다.
        </p>
        <ul>
          <li>ops-agent/README.md · docs/specs/ops-agent/aggregate-report-v1.md</li>
          <li>ops-agent/src/ops_agent/namespace_advice.py · report_interpretation.py</li>
          <li>frontend/src/lib/namespaceAdvice.ts · components/AggregateReport.tsx</li>
          <li>이전 분석 방식: docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md</li>
        </ul>
      </details>
    </div>
  );
}
