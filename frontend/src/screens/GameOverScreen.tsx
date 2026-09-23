import { strings } from '../strings';

interface Props {
  streak: number;
  expectedAnswer: string | null;
  onSave: () => void;
  onSkip: () => void;
}

export function GameOverScreen({ streak, expectedAnswer, onSave, onSkip }: Props) {
  return (
    <main className="screen">
      <h1>{strings.gameOver}</h1>
      <p>{strings.finalStreak(streak)}</p>
      {expectedAnswer && (
        <p>
          {strings.correctAnswerWas}: <strong>{expectedAnswer}</strong>
        </p>
      )}
      <button type="button" onClick={onSave} autoFocus>
        {strings.saveScore}
      </button>
      <button type="button" onClick={onSkip}>
        {strings.skip}
      </button>
    </main>
  );
}
