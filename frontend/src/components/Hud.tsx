import { useStrings } from '../language/languageState';
import { LifeMeter } from './LifeMeter';

interface Props {
  number: number;
  streak: number;
  lives: number;
  combo: number;
  lifeCombo: number;
  maxLives: number;
  // The last answer was correct: the score pops.
  scored: boolean;
}

// The line at the top of the question screen: question number, 1UPs and score.
export function Hud({ number, streak, lives, combo, lifeCombo, maxLives, scored }: Props) {
  const strings = useStrings();
  return (
    <header className="hud">
      <p className="hud__item">{strings.questionNumber(number)}</p>
      <LifeMeter lives={lives} combo={combo} lifeCombo={lifeCombo} maxLives={maxLives} />
      {/* The key on <strong> restarts the pop animation whenever the score changes. */}
      <p className="hud__item hud__item--streak">
        {strings.streakLabel}{' '}
        <strong key={streak} className={scored ? 'streak-value streak-value--up' : 'streak-value'}>
          {strings.streakValue(streak)}
        </strong>
      </p>
    </header>
  );
}
