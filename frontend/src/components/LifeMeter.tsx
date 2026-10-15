import { type CSSProperties } from 'react';

import { useStrings } from '../language/languageState';

// The same numbers as LIFE_COMBO and MAX_LIVES in backend/app/game/rules.py.
export const LIFE_COMBO = 5;
export const MAX_LIVES = 3;

interface Props {
  lives: number;
  // Correct answers in a row towards the next 1UP.
  combo: number;
}

// The 1UPs in stock as hearts. The next empty heart fills from the bottom with every
// correct answer in a row, so stock and progress fit into one small row.
export function LifeMeter({ lives, combo }: Props) {
  const strings = useStrings();
  return (
    <span className="life-meter" role="img" aria-label={strings.lifeMeterLabel(lives, combo)}>
      {Array.from({ length: MAX_LIVES }, (_, index) => {
        if (index < lives) return <Heart key={index} fill={1} />;
        return <Heart key={index} fill={index === lives ? combo / LIFE_COMBO : 0} />;
      })}
    </span>
  );
}

function Heart({ fill }: { fill: number }) {
  // --fill: the filled share from the bottom, used by the gradient in global.css.
  const style = { '--fill': `${String(Math.round(fill * 100))}%` } as CSSProperties;
  const className = fill >= 1 ? 'heart heart--full' : 'heart';
  return (
    <span className={className} style={style} aria-hidden="true">
      ♥
    </span>
  );
}
