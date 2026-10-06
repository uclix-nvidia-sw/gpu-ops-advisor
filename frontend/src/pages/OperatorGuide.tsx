import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Notice, PageHead, Panel } from '../components/ui';
import { topicId, topics } from '../lib/live';
import { reportKinds, topicDisplayBases } from '../lib/reportKinds';

// Keep current behavior distinct from the development goals in specification 12.
const topicGuides = [
  {
    purpose: '어떤 GPU가 관측됐고 메모리·온도는 어땠는지 확인합니다.',
    examples: [
      '이 기간에 클러스터에서 관측된 GPU는 몇 대인가?',
      '관측된 GPU 중 기간 평균 온도가 가장 높은 장비는 무엇인가?',
    ],
    result: '관측된 GPU 수와 GPU별 VRAM·온도의 시간 가중 평균을 제공합니다.',
    inputs: 'GPU 신원, VRAM, 온도 관측이 필요합니다.',
    limit:
      '전체 장비 목록의 완전성이나 장비 추가·제거 이력은 확정하지 않습니다. 장치 VRAM을 Pod의 메모리 실사용량으로 읽지 마세요.',
    next: '누락된 GPU와 원본 지표의 단위를 확인한 뒤 장비 목록·변경 기록과 대조하세요.',
    queries: 'D01 · D03 · D04. 계산에 사용하지 않는 Pod 신원 D06은 조회하지 않습니다.',
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
      '사건 ID 중복을 제거한 건수, 사건이 둘 이상일 때 조회된 사건들의 평균 발생 간격, 공개 RCA 참조를 제공합니다.',
    inputs: '기간·범위에 해당하는 저장 Incident와 공개 RCA 결과를 사용합니다.',
    limit:
      '현재 간격은 서로 다른 장비·사건이 섞일 수 있어 동일 고장의 재발 주기로 단정하면 안 됩니다. 관측시간당 발생률과 전체 정비 순위는 아직 산출하지 않습니다.',
    next: '장비·사건 종류와 RCA의 원인 판단 수준을 따로 확인하세요. 보고서 요청이 새 RCA를 실행하지는 않습니다.',
    queries: 'DB 사건·공개 RCA 스냅샷 + D10',
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
      'DB 사건 스냅샷 + D08 · D06 · D13. 고정된 사건 목록이 0건이면 D13 로그 조회를 생략합니다. 다른 소주제에 필요한 조회는 유지합니다.',
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
      'Namespace별로 연결된 GPU의 평균 활동률과 연결 시간은 얼마인가?',
    ],
    result:
      '클러스터별 관측 GPU·연결 확인 GPU·누적 연결 시간을 먼저 보여주고, 연결된 Namespace별 GPU 수·유효 GPU·시간·평균 활동률을 제공합니다.',
    inputs:
      '같은 시각의 GPU–Pod 연결·Pod UID·Namespace·노드·GPU 신원과 활동률이 필요합니다. 할당 이력은 공유 여부 확인에 사용합니다.',
    limit:
      'Namespace의 실제 소비량·독점 할당량·회수 가능량이 아닙니다. 공유/MIG·신원/값 충돌 구간은 평균에서 제외하며, 혼합 GPU 모델 등은 평균을 보류합니다. 프로젝트별 배분은 이 기본 분석에 포함되지 않습니다.',
    next: 'Namespace만 궁금하면 이 종류만 선택하고, 결과의 적용 집계·유효시간·제외 사유를 확인하세요. Pod 라벨 없는 관측은 유휴로 단정하지 않습니다. 수집 실패·신원 불일치 등 실제 미충족 근거가 있으면 부분 산출로 표시합니다.',
    queries:
      'criteria 1.2: D01 · D02 · D06 · D08. namespace 또는 cluster+namespace만 적용. 구 criteria 경로는 D08 · D01 · D06 · D12이며 결과가 다릅니다.',
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
    result: '수집 상태 지표가 정상(up=1)이었던 대상별 시간을 합산하고 수집 상태를 제공합니다.',
    inputs:
      '기간 내 수집 상태 지표가 필요합니다. 전체 커버리지에는 기대 대상 목록과 시간이 추가로 필요합니다.',
    limit:
      '현재 전체 커버리지는 분모 부족으로 산출하지 않습니다. 대상·초 합계는 경과 시간이나 GPU 사용시간이 아닙니다.',
    next: '보고서의 분석 진행 상세에서 query·CPC별 빈 응답·미완료 구간과 사유를 확인하세요. 이 진단은 O11을 선택하지 않아도 기록된 보고서에서 볼 수 있습니다.',
    queries: 'D10; 전체 커버리지 분모 미구현',
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
        eyebrow="OPERATOR GUIDE"
        title="운영자 가이드"
        description="GPU 운영 분석의 주제, 필요한 근거와 결과를 읽는 방법입니다."
        actions={
          <Link className="button primary" to="/reports/new">
            새 보고서 만들기
          </Link>
        }
      />
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
      <section id="guide-start" hidden={selected !== 'start'} aria-label="시작 방법">
        <Panel title="처음에는 이렇게 요청하세요" className="guide-section">
          <div className="guide-body">
            <ol>
              <li>
                <strong>전체 종합 또는 필요한 종류를 선택하세요.</strong> 처음에는 7개 종류가 모두
                선택돼 11개 소주제를 담습니다. 직접 선택에서는 여러 종류를 함께 고를 수 있습니다.
                종류별로 따로 실행하는 것이 아니라 선택한 내용을 보고서 한 장으로 만듭니다.
              </li>
              <li>
                <strong>관측 범위와 분석 날짜를 확인하세요.</strong> CPC는 클러스터입니다. 전체
                클러스터 또는 필요한 클러스터·Namespace를 선택하세요. 모든 표시 시각은 한국 시간
                기준이며 요청 접수 시각·분석 대상 기간·보고서 실행시간은 서로 다릅니다. 기간 밖의
                LLM 추론 부하는 해당 보고서 수치에 포함되지 않습니다.
              </li>
              <li>
                <strong>반복 보고서는 자동 보고서 설정에서 등록하세요.</strong> 일간·주간·월간 중
                고르며 직전 완료된 달력 기간을 분석합니다. 즉시 보고서는 시작일과 종료일을 날짜로
                정합니다. 종료일을 포함하며 같은 날짜면 1일(24시간)입니다. 기본값은 어제 하루이고
                최대 31일까지 선택합니다. 긴 기간도 요청할 수 있지만 적용된 기간·조회·시간 한도와
                데이터 양에 따라 일부 수집이 끝나지 않을 수 있습니다.
              </li>
              <li>
                <strong>접수 후 실행 상태와 결과 품질을 따로 확인하세요.</strong> 작업 이력의 종류는
                ‘운영 분석 보고서’로 표시합니다. ‘직접 요청’은 운영자가 요청한 보고서, ‘자동 생성’은
                등록한 일정으로 만들어진 보고서입니다. 실행 완료여도 결과가 부분 산출·근거 부족일 수
                있으므로 소주제별 이유를 확인하세요.
              </li>
            </ol>
            <Link className="text-link" to="/reports">
              보고서 이력으로 이동
            </Link>
          </div>
        </Panel>
      </section>
      <section
        id="guide-topics"
        hidden={selected !== 'topics'}
        aria-labelledby="guide-topics-title"
      >
        <h2 id="guide-topics-title">궁금한 보고서 종류를 고르세요</h2>
        <p>종류를 누르면 해당 설명과 포함된 분석만 아래에 표시합니다.</p>
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
              <strong>{item.name}</strong>
            </button>
          ))}
        </div>
        <section id="guide-kind-content" aria-labelledby="guide-kind-title" key={kind.id}>
          <Panel className="guide-section guide-kind-panel">
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
                  <th scope="row">포함된 세부 분석 · {kind.topicIds.length}개</th>
                  <td>
                    <p>질문 예시를 보고, 펼치면 계산 기준과 필요한 자료를 확인할 수 있습니다.</p>
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
          </Panel>
        </section>
        <Notice>
          여기서는 한 종류씩 설명을 봅니다. 실제 보고서 요청에서는 7개 종류를 여러 개 선택하거나
          전체 종합으로 11개 소주제를 한 장에 담을 수 있습니다. 전체 선택이 수집량 감소를 뜻하지는
          않으며, 자료가 부족한 소주제도 이유와 함께 남습니다.
        </Notice>
      </section>
      <section
        id="guide-values"
        hidden={selected !== 'values'}
        className="guide-section"
        aria-label="수치 읽는 법"
      >
        <Panel title="수치를 이렇게 읽으세요">
          <dl className="guide-body guide-topic-fields">
            <dt>0% / 산출 불가 / 미계산</dt>
            <dd>
              0%는 유효한 관측으로 계산된 값입니다. 아주 작은 값은 표시 자릿수에서 반올림될 수
              있습니다. 산출 불가는 필요한 데이터·조건을 충족하지 못한 값(null), 미계산은 저장
              결과에 해당 지표가 없는 경우입니다. 모델이 메모리에 올라와 있거나 Pod가 Running이어도
              분석 기간의 활동률은 0%일 수 있습니다.
            </dd>
            <dt>연결 GPU 평균 활동률</dt>
            <dd>
              귀속을 확인할 수 있는 연결 구간과 활동 표본을 겹쳐 시간 가중으로 계산합니다. 짧은
              부하가 평균에서 작게 보일 수 있으며 Namespace의 실제 연산 소비 비율과는 다릅니다.
            </dd>
            <dt>연결 GPU 수</dt>
            <dd>
              기간 중 한 번이라도 연결이 확인된 고유 GPU 대수입니다. 동시에 사용한 최대 대수가
              아닙니다.
            </dd>
            <dt>GPU·시간</dt>
            <dd>
              GPU별 시간을 누적한 단위입니다. 예를 들어 GPU 4대가 2시간 연결됐다면 8 GPU·시간입니다.
              2시간 보고서에서 약 8 GPU·시간이 나와도 기간 오류는 아닙니다. 관측 공백·제외 구간으로
              값이 줄 수 있고, 공유 GPU는 Namespace 사이에 중복될 수 있습니다.
            </dd>
            <dt>소주제별 표시 기준</dt>
            <dd>
              한 보고서 안에서도 기준이 다릅니다. Namespace 현황은 클러스터·Namespace별,
              메모리·온도는 GPU 장비별, 에너지는 선택 범위 전체 GPU의 합계입니다. 모든 수치를
              Namespace별 사용량으로 읽거나 서로 다른 단위끼리 더하지 마세요.
            </dd>
            <dt>실행 상태</dt>
            <dd>
              실행 대기·실행 중·재시도 대기·실행 완료는 작업의 진행 상태입니다. 실행 실패·기한
              만료는 상세 화면에서 종료 사유를 확인하세요. 실행 완료가 모든 분석의 성공을 뜻하지는
              않습니다.
            </dd>
            <dt>결과 품질</dt>
            <dd>
              산출 가능은 해당 계산의 근거가 충족됐다는 뜻이며 장비가 정상이라는 판정은 아닙니다.
              부분 산출은 일부 값이나 판단에 제한이 있고, 근거 부족은 계산에 필요한 자료·조건이
              부족한 상태입니다. 미발행은 아직 공개 결과가 없다는 뜻입니다. 예를 들어 ‘실행 완료’와
              ‘부분 산출’이 함께 나올 수 있습니다. 자료가 없다는 사실을 정상 또는 0으로 바꾸지
              않습니다.
            </dd>
            <dt>AI 해석과 권고</dt>
            <dd>
              현재 수치는 코드가 계산하고 AI는 검증된 문장의 우선순위를 정합니다. AI 편집 실패 시
              기본 보고서를 사용할 수 있습니다. 판단 보류 권고는 조치 승인이나 수행 완료가 아니며
              GPU 회수·설정 변경은 자동 실행하지 않습니다.
            </dd>
          </dl>
        </Panel>
      </section>
      <section
        id="guide-missing"
        hidden={selected !== 'missing'}
        className="guide-section"
        aria-labelledby="guide-missing-title"
      >
        <h2 id="guide-missing-title">근거 부족이면 무엇부터 확인하나요?</h2>
        <p>
          보고서 본문의 <strong>분석 진행 상세</strong>를 펼쳐 해당 주제의 부족 사유와 query·CPC별
          수집 구간을 확인하세요. 근거 부족만으로 연결 장애를 단정할 수 없습니다.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>확인한 상태</th>
                <th>뜻과 다음 확인</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>조회 오류·연결 실패</td>
                <td>기록된 오류 코드와 대상 데이터 소스·접속 설정을 확인합니다.</td>
              </tr>
              <tr>
                <td>빈 응답</td>
                <td>
                  조회는 끝났지만 조건에 맞는 표본이 없었습니다. 기간·Namespace·지표 이름과 보존
                  기간을 대조합니다.
                </td>
              </tr>
              <tr>
                <td>조회 한도·시간 소진</td>
                <td>
                  계획 중단 또는 일부 구간 미완료입니다. 저장된 적용 한도·실제 호출 수·미완료 기간을
                  확인합니다. 연결 실패와 구분하고 범위를 줄이거나 운영 설정을 점검합니다.
                </td>
              </tr>
              <tr>
                <td>할당 이력·신원·활동 부족</td>
                <td>
                  필요한 지표, 동일 시각의 GPU–Pod UID 연결, 활동률 단위를 확인합니다. 연결 관측이
                  있어도 독점 할당 근거는 없을 수 있습니다.
                </td>
              </tr>
              <tr>
                <td>조치 기록·비교 기간 미지정</td>
                <td>
                  조치 전후 비교의 입력 조건이 없는 상태이며 연결 장애가 아닙니다. 직접 요청에서
                  수행한 조치 ID와 비교 기간을 입력하세요. 자동보고서는 이 조건을 임의로 만들지 않고
                  부족 사유를 남기며 다른 소주제 분석을 계속합니다.
                </td>
              </tr>
              <tr>
                <td>공유·모델 혼합·값 충돌</td>
                <td>
                  관측은 있지만 귀속이나 평균 비교 조건이 맞지 않습니다. 제외 사유와 유효시간을
                  확인하며 억지로 평균을 채우지 않습니다.
                </td>
              </tr>
              <tr>
                <td>현재 미지원·미구현</td>
                <td>
                  선택한 주제·집계와 위 주제별 제한을 확인합니다. 데이터나 연결을 복구해도 아직
                  구현하지 않은 분석이 생기지는 않습니다.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="muted">
          수집 응답 완료는 표본이 연속적이거나 계산·권고가 가능하다는 뜻이 아닙니다. 구 보고서에
          수집 진단이 없으면 조회 여부를 추정하지 않습니다.
        </p>
      </section>
      <details className="guide-sources">
        <summary>안내 기준과 개발 범위 · 2026-10-06</summary>
        <p>
          12번 보고서 Agent 설계서의 현재 구현·§3 주제 표, 04번 공통 판단 명세와 Ops Worker 코드를
          대조했습니다. 종합·다중 선택과 소주제별 기준, 불필요한 조회 생략을 반영했습니다. 임의의
          모든 그룹별 재집계나 자유 생성형 종합 조언을 구현했다는 뜻은 아닙니다. 서버 버전·프로필에
          따라 결과가 다를 수 있습니다.
        </p>
        <ul>
          <li>docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md</li>
          <li>docs/specs/common/04_Agent_동작_판단_명세서.md</li>
          <li>
            ops-agent/src/ops_agent/workflow.py · namespace_usage.py · collection.py · report.py
          </li>
          <li>shared/python/src/agent_common/calculations.py</li>
        </ul>
      </details>
    </div>
  );
}
