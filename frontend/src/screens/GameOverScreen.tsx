import { strings } from '../strings';

interface Props {
  streak: number;
  expectedAnswer: string | null;
  onSave: () => void;
  onSkip: () => void;
}

export function GameOverScreen({ streak, expectedAnswer, onSave, onSkip }: Props) {
  return (
    <main className="screen screen--game-over">
      <h1 className="game-over">{strings.gameOver}</h1>
      <p className="score">
        <span className="score__label">{strings.finalStreak}</span>
        <span className="score__value">{strings.streakValue(streak)}</span>
      </p>
      {expectedAnswer && (
        <section className="answer-reveal">
          <p className="answer-reveal__label">{strings.correctAnswerWas}</p>
          <p className="answer-reveal__value">{expectedAnswer}</p>
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
