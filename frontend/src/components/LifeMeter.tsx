import { useStrings } from '../language/languageState';

// The same numbers as LIFE_COMBO and MAX_LIVES in backend/app/game/rules.py.
export const LIFE_COMBO = 5;
export const MAX_LIVES = 3;

interface Props {
  lives: number;
  // Correct answers in a row towards the next 1UP.
  combo: number;
}

// The 1UPs in stock as hearts, and a bar that fills with every correct answer in a row.
export function LifeMeter({ lives, combo }: Props) {
  const strings = useStrings();
  const full = lives >= MAX_LIVES;
  return (
    <div className="life-meter" role="status" aria-label={strings.lifeMeterLabel(lives, combo)}>
      <span className="life-meter__hearts" aria-hidden="true">
        {Array.from({ length: MAX_LIVES }, (_, index) => (
          <span key={index} className={index < lives ? 'heart heart--full' : 'heart heart--empty'}>
            ♥
          </span>
        ))}
      </span>
      <span className="life-meter__combo" aria-hidden="true">
        {Array.from({ length: LIFE_COMBO }, (_, index) => (
          <span
            key={index}
            className={index < combo ? 'combo-cell combo-cell--on' : 'combo-cell'}
          />
        ))}
      </span>
      <span className="life-meter__hint" aria-hidden="true">
        {full ? strings.livesFull : strings.comboToNext(LIFE_COMBO - combo)}
      </span>
    </div>
  );
}
