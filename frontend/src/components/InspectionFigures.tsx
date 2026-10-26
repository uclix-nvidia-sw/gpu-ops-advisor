import { useState } from 'react';
import { FIGURES, figureUrl, type FigureId } from '../lib/inspectionFigures';
import { Modal } from './ui';

const NOTE =
  '실제 장비의 구성에 맞는 예시를 참고하세요. 표시 영역은 실제 장치 위치를 특정하지 않습니다.';

/** Small inspection-area previews under a response step; the large view plays on request. */
export function InspectionFigures({ ids }: { ids: FigureId[] }) {
  const [open, setOpen] = useState<FigureId | null>(null);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  // A missing asset leaves the step text alone.
  if (failed) return null;
  return (
    <div className="rca-figures" role="group" aria-label="점검 위치 그림">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className="rca-figure-thumb"
          onClick={() => {
            setPlaying(false);
            setOpen(id);
          }}
        >
          <img
            src={figureUrl(id, 'png')}
            alt=""
            width={96}
            height={64}
            loading="lazy"
            onError={() => setFailed(true)}
          />
          <span>
            {FIGURES[id].title}
            <small>크게 보기</small>
          </span>
        </button>
      ))}
      <p className="rca-figure-note">{NOTE}</p>
      {open && (
        <Modal title={FIGURES[open].title} wide onClose={() => setOpen(null)}>
          <div className="rca-figure-view">
            <div className="rca-figure-bar">
              <span className="muted">{FIGURES[open].caption}</span>
              <button
                type="button"
                className="button rca-figure-play"
                onClick={() => setPlaying(!playing)}
              >
                {playing ? '정지' : '구조 보기'}
              </button>
            </div>
            <img
              src={figureUrl(open, playing ? 'webp' : 'png')}
              alt={`${FIGURES[open].title} 점검 영역 그림: ${FIGURES[open].caption}`}
              width={900}
              height={600}
            />
            <p className="muted">{NOTE}</p>
          </div>
        </Modal>
      )}
    </div>
  );
}
