// Fleet component reports: what the alert target is and which Unhealthy reason fired.
// Reason strings come from the deployed Fleet source (v1.5.0-rc.1) Check() and
// kmsg matchers; `branch` is the label the Runbook's 판단 step uses for that reason.

export interface ComponentReason {
  label: string;
  matches: string[];
  branch?: string;
}

interface ComponentInfo {
  /** Short form for headers. */
  short: string;
  /** What the alert points at and where to find the device. */
  target: string;
  reasons: ComponentReason[];
}

const NODE_WIDE = (what: string) => ({
  short: '노드 전체',
  target: `노드 전체 ${what} 보고이며 특정 장치를 가리키지 않습니다`,
});
const DCGM: ComponentInfo = {
  short: 'GPU는 오류 로그 원문에',
  target: '문제 GPU(UUID)는 오류 로그 원문의 extra_info.dcgm_incidents에 있습니다',
  reasons: [
    { label: 'DCGM 건강 점검 실패(FAIL)', matches: ['health failure'] },
    { label: 'DCGM 건강 점검 결과 조회 실패', matches: ['failed to get DCGM'] },
  ],
};
const DISK_IO = '버퍼 I/O·superblock 쓰기 오류·범위 밖 접근';
const NVME = 'NVMe 타임아웃·경로 실패·장치 비활성화';

const COMPONENTS: Record<string, ComponentInfo> = {
  disk: {
    short: '대상 디스크: 보고에 이름 없음',
    target:
      '대상 디스크·파티션 이름은 Fleet 보고에 없습니다 — dmesg의 EXT4-fs·nvme·md 줄에서 장치 이름을 확인합니다',
    reasons: [
      {
        label: '읽기 전용 재마운트',
        matches: ['remounted as read-only'],
        branch: '읽기 전용 재마운트',
      },
      { label: 'RAID 배열 실패', matches: ['RAID array has failed'], branch: 'RAID 배열 실패' },
      { label: 'NVMe 경로 실패', matches: ['no available path'], branch: NVME },
      { label: 'NVMe I/O 타임아웃', matches: ['I/O timeout detected'], branch: NVME },
      { label: 'NVMe 장치 비활성화', matches: ['disabled after reset failure'], branch: NVME },
      { label: '장치 범위 밖 접근', matches: ['beyond device boundaries'], branch: DISK_IO },
      { label: '버퍼 I/O 오류', matches: ['Buffer I/O error'], branch: DISK_IO },
      { label: 'superblock 쓰기 오류', matches: ['writing superblock'], branch: DISK_IO },
    ],
  },
  cpu: {
    ...NODE_WIDE('CPU 상태'),
    reasons: [
      { label: 'CPU 사용률 계산 실패', matches: ['error calculating CPU usage'] },
      { label: 'load average 계산 실패', matches: ['error calculating load average'] },
    ],
  },
  memory: {
    ...NODE_WIDE('메모리 상태'),
    reasons: [
      { label: '가상 메모리 정보 조회 실패', matches: ['error getting virtual memory'] },
      { label: 'BPF JIT 버퍼 조회 실패', matches: ['error getting bpf jit buffer'] },
    ],
  },
  os: {
    ...NODE_WIDE('운영체제 상태'),
    reasons: [
      { label: '좀비 프로세스 과다', matches: ['too many zombie processes'] },
      { label: '실행 중 PID 과다', matches: ['too many running pids'] },
      { label: '파일 핸들 과다', matches: ['too many allocated file handles'] },
      { label: 'OS 정보 조회 실패', matches: ['error getting'] },
    ],
  },
  'network-ethernet': {
    short: '끊긴 인터페이스는 보고 사유에',
    target: '끊긴 인터페이스 이름은 보고 사유 괄호 안에 있습니다',
    reasons: [{ label: '모든 물리 이더넷 링크 끊김', matches: ['all ethernet links are down'] }],
  },
  'accelerator-nvidia-infiniband': {
    short: 'IB 장치는 보고 사유에',
    target: '문제 IB 장치(mlx5_N 등) 이름은 보고 사유에 있습니다',
    reasons: [
      { label: '활성 포트·속도 부족', matches: ['port(s) are active'] },
      { label: '포트 장시간 다운', matches: ['down too long'] },
      { label: '포트 flapping(ACTIVE↔DOWN 반복)', matches: ['flapping between'] },
      {
        label: 'IB 정보 조회 실패',
        matches: ['error loading infiniband', 'error getting ib', 'error inserting ib'],
      },
    ],
  },
  library: {
    short: 'NVIDIA 드라이버 라이브러리',
    target: '노드의 NVIDIA 드라이버 사용자 공간 라이브러리(libnvidia-ml.so, libcuda.so)',
    reasons: [{ label: 'NVIDIA 라이브러리 없음', matches: ['does not exist'] }],
  },
  'accelerator-nvidia-nccl': {
    ...NODE_WIDE('커널 로그 읽기'),
    reasons: [{ label: '커널 로그 읽기 실패', matches: ['failed to read kmsg'] }],
  },
  'accelerator-nvidia-peermem': {
    ...NODE_WIDE('nvidia-peermem 모듈 확인'),
    reasons: [{ label: 'peermem 모듈 상태 확인 실패', matches: ['error checking peermem'] }],
  },
  'accelerator-nvidia-persistence-mode': {
    short: 'GPU: 보고에 없음',
    target: '어느 GPU인지 Fleet 보고에 없습니다 — nvidia-smi -L·nvidia-smi -q로 확인합니다',
    reasons: [
      { label: 'GPU 접근 상실', matches: ['GPU lost'], branch: 'GPU lost' },
      { label: 'GPU 리셋 필요', matches: ['GPU requires reset'], branch: 'GPU requires reset' },
      {
        label: 'persistence mode 조회 오류',
        matches: ['error getting persistence mode', 'failed to get DCGM persistence-mode field'],
        branch: 'persistence mode 조회 오류',
      },
    ],
  },
};

const DEFAULT_TARGET = {
  short: '장치 정보 없음',
  target: '보고에 장치 정보가 없어 대응 순서의 즉시 확인으로 찾습니다',
};

export function componentInfo(component: string) {
  const info =
    COMPONENTS[component] || (component.startsWith('accelerator-nvidia-dcgm-') ? DCGM : null);
  return info || { ...DEFAULT_TARGET, reasons: [] as ComponentReason[] };
}

/** The reasons a report message names; several may come joined in one message. */
export function matchedReasons(component: string, message: string) {
  const text = message.toLowerCase();
  return componentInfo(component).reasons.filter((r) =>
    r.matches.some((m) => text.includes(m.toLowerCase())),
  );
}
