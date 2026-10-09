import { strings } from '../strings';

interface Props {
  streak: number;
  expectedAnswer: string | null;
  explanation: string | null;
  timedOut: boolean;
  onSave: () => void;
  onSkip: () => void;
}

export function GameOverScreen({
  streak,
  expectedAnswer,
  explanation,
  timedOut,
  onSave,
  onSkip,
}: Props) {
  return (
    <main className="screen screen--game-over">
      {timedOut && <p className="time-up">{strings.timeUp}</p>}
      <h1 className="game-over">{strings.gameOver}</h1>
      <p className="score">
        <span className="score__label">{strings.finalStreak}</span>
        <span className="score__value">{strings.streakValue(streak)}</span>
      </p>
      {expectedAnswer && (
        <section className="answer-reveal">
          <p className="answer-reveal__label">{strings.correctAnswerWas}</p>
          <p className="answer-reveal__value">{expectedAnswer}</p>
          {explanation && <p className="answer-reveal__explanation">{explanation}</p>}
        </section>
      )}
      <button type="button" className="button button--primary" onClick={onSave} autoFocus>
        {strings.saveScore}
      </button>
      <button type="button" className="button button--secondary" onClick={onSkip}>
        {strings.skip}
      </button>
    </main>
  );
}
