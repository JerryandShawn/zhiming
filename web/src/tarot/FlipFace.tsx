import type { CSSProperties } from 'react';
import { useTarotReducedMotion } from './useTarotMotion';

export function FlipFace({
  revealed,
  frontImage,
  alt,
  reversed = false,
  delay = 0,
  backImage = '/static/tarot/back.svg',
}: {
  revealed: boolean;
  frontImage?: string;
  alt: string;
  reversed?: boolean;
  delay?: number;
  backImage?: string;
}) {
  const reduced = useTarotReducedMotion();
  return (
    <span
      className={`tarot-flip ${revealed ? 'is-revealed' : ''} ${reduced ? 'no-motion' : ''}`}
      data-reduced-motion={reduced ? 'true' : 'false'}
      style={{ '--tarot-reveal-delay': `${reduced ? 0 : delay}ms` } as CSSProperties}>
      <span className="tarot-flip-rotor">
        <img
          className="tarot-flip-back"
          src={backImage}
          alt={revealed ? '' : '不透明的塔罗牌背'}
          aria-hidden={revealed || undefined}
        />
        {/* Hidden identities and their SVG URLs must never enter the unrevealed DOM. */}
        {revealed && frontImage && (
          <img className={`tarot-flip-front ${reversed ? 'reversed' : ''}`} src={frontImage} alt={alt} />
        )}
      </span>
    </span>
  );
}
