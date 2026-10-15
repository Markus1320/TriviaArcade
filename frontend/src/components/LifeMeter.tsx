import { type CSSProperties } from 'react';

import { useStrings } from '../language/languageState';

interface Props {
  lives: number;
  // Correct answers in a row towards the next 1UP.
  combo: number;
  // From the server's settings: correct answers in a row for a 1UP, most 1UPs in stock.
  lifeCombo: number;
  maxLives: number;
}

// The 1UPs in stock as hearts. The next empty heart fills from the bottom with every
// correct answer in a row, so stock and progress fit into one small row.
export function LifeMeter({ lives, combo, lifeCombo, maxLives }: Props) {
  const strings = useStrings();
  return (
    <span
      className="life-meter"
      role="img"
      aria-label={strings.lifeMeterLabel(lives, combo, lifeCombo)}
    >
      {Array.from({ length: maxLives }, (_, index) => {
        if (index < lives) return <Heart key={index} fill={1} />;
        return <Heart key={index} fill={index === lives ? combo / lifeCombo : 0} />;
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
