import { useCallback, useEffect, useRef, useState, type SubmitEvent } from 'react';

import { api, type Question } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

const MAX_ANSWER_LENGTH = 200;

interface Props {
  runId: string;
  onGameOver: (streak: number, expectedAnswer: string | null) => void;
}

type Phase =
  | { kind: 'loading' }
  | { kind: 'loadFailed'; message: string }
  | { kind: 'asking'; question: Question; error: string | null }
  | { kind: 'judging'; question: Question }
  | { kind: 'correct'; question: Question; streak: number };

// The next question, requested while the player still sees the "correct" verdict.
interface Prefetch {
  promise: Promise<Question>;
  ready: Question | null;
}

export function QuestionScreen({ runId, onGameOver }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [answer, setAnswer] = useState('');
  const prefetch = useRef<Prefetch | null>(null);

  const showQuestion = useCallback((question: Question) => {
    setAnswer('');
    setPhase({ kind: 'asking', question, error: null });
  }, []);

  // Only updates state once the request settles, so it can run inside an effect.
  const awaitQuestion = useCallback(
    (request: Promise<Question>) => {
      request.then(showQuestion).catch((err: unknown) => {
        setPhase({ kind: 'loadFailed', message: errorMessage(err) });
      });
    },
    [showQuestion],
  );

  useEffect(() => {
    awaitQuestion(api.nextQuestion(runId));
  }, [awaitQuestion, runId]);

  // Starts generating the next question right after a correct answer. The server keeps it
  // as the open question, so this is safe even if the player reloads before seeing it.
  const startPrefetch = () => {
    const entry: Prefetch = { promise: api.nextQuestion(runId), ready: null };
    entry.promise.then(
      (question) => {
        entry.ready = question;
      },
      () => {
        // Reported when the player asks for the question; see loadQuestion.
      },
    );
    prefetch.current = entry;
  };

  const loadQuestion = () => {
    const entry = prefetch.current;
    prefetch.current = null;
    if (entry?.ready) {
      showQuestion(entry.ready);
      return;
    }
    setPhase({ kind: 'loading' });
    // A failed prefetch rejects here too; the retry button then sends a fresh request.
    awaitQuestion(entry?.promise ?? api.nextQuestion(runId));
  };

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (phase.kind !== 'asking' || answer.trim() === '') return;
    const { question } = phase;
    setPhase({ kind: 'judging', question });
    api
      .answer(runId, answer)
      .then((result) => {
        if (result.game_over) {
          onGameOver(result.streak, result.expected_answer);
        } else {
          setPhase({ kind: 'correct', question, streak: result.streak });
          startPrefetch();
        }
      })
      .catch((err: unknown) => {
        // A judge failure pauses the run: the question stays open and can be answered again.
        setPhase({ kind: 'asking', question, error: errorMessage(err) });
      });
  };

  if (phase.kind === 'loading') {
    return (
      <main className="screen">
        <p>{strings.loadingQuestion}</p>
      </main>
    );
  }
  if (phase.kind === 'loadFailed') {
    return (
      <main className="screen">
        <p role="alert">{phase.message}</p>
        <button type="button" onClick={loadQuestion}>
          {strings.retry}
        </button>
      </main>
    );
  }

  const { question } = phase;
  const streak = phase.kind === 'correct' ? phase.streak : question.streak;
  return (
    <main className="screen">
      <p className="status-line">
        <span>{strings.questionNumber(question.number)}</span>
        <span>{strings.streak(streak)}</span>
      </p>
      <h2>{question.text}</h2>
      {phase.kind === 'correct' ? (
        <>
          <p className="verdict">{strings.correct}</p>
          <button type="button" onClick={loadQuestion} autoFocus>
            {strings.nextQuestion}
          </button>
        </>
      ) : (
        <form onSubmit={submit}>
          <label htmlFor="answer">{strings.answerLabel}</label>
          <input
            id="answer"
            value={answer}
            onChange={(event) => {
              setAnswer(event.target.value);
            }}
            maxLength={MAX_ANSWER_LENGTH}
            autoComplete="off"
            autoFocus
            disabled={phase.kind === 'judging'}
          />
          <button type="submit" disabled={phase.kind === 'judging' || answer.trim() === ''}>
            {phase.kind === 'judging' ? strings.judging : strings.submit}
          </button>
          {phase.kind === 'asking' && phase.error && <p role="alert">{phase.error}</p>}
        </form>
      )}
    </main>
  );
}
