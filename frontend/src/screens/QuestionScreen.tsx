import { useCallback, useEffect, useRef, useState, type SubmitEvent } from 'react';

import { api, type AnswerResult, type Question } from '../api/client';
import { useSound } from '../audio/soundState';
import { TimeBar, URGENT_MS } from '../components/TimeBar';
import { errorMessage } from '../errors';
import { strings } from '../strings';
import { useCountdown } from '../useCountdown';

const MAX_ANSWER_LENGTH = 200;

interface Props {
  runId: string;
  onGameOver: (
    streak: number,
    expectedAnswer: string | null,
    timedOut: boolean,
    explanation: string | null,
  ) => void;
}

// deadline: performance.now() timestamp when the time is up, null without a time limit.
type Phase =
  | { kind: 'loading' }
  | { kind: 'loadFailed'; message: string }
  | { kind: 'asking'; question: Question; error: string | null; deadline: number | null }
  | { kind: 'judging'; question: Question }
  | { kind: 'correct'; question: Question; streak: number; explanation: string | null };

// The next question, requested while the player still sees the "correct" verdict.
interface Prefetch {
  promise: Promise<Question>;
  ready: Question | null;
}

export function QuestionScreen({ runId, onGameOver }: Props) {
  const { play } = useSound();
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [answer, setAnswer] = useState('');
  const prefetch = useRef<Prefetch | null>(null);

  const fail = useCallback((err: unknown) => {
    setPhase({ kind: 'loadFailed', message: errorMessage(err) });
  }, []);

  // Tells the server the open question is now shown, which starts its time limit, then shows
  // it. The response is the open question itself, so a prefetched copy is not needed here.
  // After a reload the clock keeps running, so seconds_left may already be low or zero.
  const showQuestion = useCallback(() => {
    api
      .startQuestion(runId)
      .then((started) => {
        setAnswer('');
        setPhase({
          kind: 'asking',
          question: started,
          error: null,
          deadline: deadlineIn(started.seconds_left),
        });
      })
      .catch(fail);
  }, [runId, fail]);

  // Only updates state once the request settles, so it can run inside an effect.
  const awaitQuestion = useCallback(
    (request: Promise<Question>) => {
      request
        .then(() => {
          showQuestion();
        })
        .catch(fail);
    },
    [showQuestion, fail],
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
      showQuestion();
      return;
    }
    setPhase({ kind: 'loading' });
    // A failed prefetch rejects here too; the retry button then sends a fresh request.
    awaitQuestion(entry?.promise ?? api.nextQuestion(runId));
  };

  const endRun = (result: AnswerResult) => {
    play('wrong');
    play('gameOver');
    onGameOver(result.streak, result.expected_answer, result.timed_out, result.explanation);
  };

  const sendAnswer = (text: string) => {
    if (phase.kind !== 'asking' || text.trim() === '') return;
    const { question } = phase;
    setPhase({ kind: 'judging', question });
    api
      .answer(runId, text)
      .then((result) => {
        if (result.game_over) {
          endRun(result);
        } else {
          play('correct');
          setPhase({
            kind: 'correct',
            question,
            streak: result.streak,
            explanation: result.explanation,
          });
          startPrefetch();
        }
      })
      .catch((err: unknown) => {
        // A judge failure pauses the run: the question stays open and can be answered again.
        // The server gives a fresh time limit for it.
        setPhase({
          kind: 'asking',
          question,
          error: errorMessage(err),
          deadline: deadlineIn(question.time_limit_seconds),
        });
      });
  };

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    sendAnswer(answer);
  };

  // Time is up: whatever the player typed is sent to the judge; with nothing typed the run ends.
  const expire = () => {
    if (phase.kind !== 'asking') return;
    if (answer.trim() !== '') {
      sendAnswer(answer);
      return;
    }
    setPhase({ kind: 'judging', question: phase.question });
    api.timeOut(runId).then(endRun).catch(fail);
  };

  const remainingMs = useCountdown(phase.kind === 'asking' ? phase.deadline : null, {
    onSecond: (secondsLeft) => {
      if (secondsLeft * 1000 <= URGENT_MS) play('tick');
    },
    onExpire: expire,
  });

  if (phase.kind === 'loading') {
    return (
      <main className="screen screen--question">
        <p className="loading">
          <span className="blink">{strings.loadingQuestion}</span>
        </p>
      </main>
    );
  }
  if (phase.kind === 'loadFailed') {
    return (
      <main className="screen screen--question">
        <p className="message message--error" role="alert">
          {phase.message}
        </p>
        <button type="button" className="button button--primary" onClick={loadQuestion} autoFocus>
          {strings.retry}
        </button>
      </main>
    );
  }

  const { question } = phase;
  const correct = phase.kind === 'correct';
  const streak = correct ? phase.streak : question.streak;
  const limit = question.time_limit_seconds;
  return (
    <main className="screen screen--question">
      <header className="hud">
        <p className="hud__item">{strings.questionNumber(question.number)}</p>
        <p className="hud__item hud__item--streak">
          {strings.streakLabel}{' '}
          {/* The key restarts the pop animation whenever the streak changes. */}
          <strong
            key={streak}
            className={correct ? 'streak-value streak-value--up' : 'streak-value'}
          >
            {strings.streakValue(streak)}
          </strong>
        </p>
      </header>
      {!correct && limit !== null && remainingMs !== null && (
        <TimeBar remainingMs={remainingMs} limitMs={limit * 1000} />
      )}
      {/* After a correct answer the box shows what there is to learn, not the question again. */}
      <section className={correct ? 'question-box question-box--correct' : 'question-box'}>
        {correct && phase.explanation ? (
          <p className="question-text">{phase.explanation}</p>
        ) : (
          <h2 className="question-text">{question.text}</h2>
        )}
      </section>
      {correct ? (
        <>
          <p className="verdict verdict--correct" role="status">
            {strings.correct}
          </p>
          <button type="button" className="button button--primary" onClick={loadQuestion} autoFocus>
            {strings.nextQuestion}
          </button>
        </>
      ) : (
        <form className="answer-form" onSubmit={submit}>
          <label className="field-label" htmlFor="answer">
            {strings.answerLabel}
          </label>
          <input
            id="answer"
            className="text-input"
            value={answer}
            onChange={(event) => {
              setAnswer(event.target.value);
            }}
            placeholder={strings.answerPlaceholder}
            maxLength={MAX_ANSWER_LENGTH}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            // No autoFocus: on phones it opens the keyboard, which hides the question.
            disabled={phase.kind === 'judging'}
          />
          <button
            type="submit"
            className="button button--primary"
            disabled={phase.kind === 'judging' || answer.trim() === ''}
          >
            {phase.kind === 'judging' ? (
              <span className="blink">{strings.judging}</span>
            ) : (
              strings.submit
            )}
          </button>
          {phase.kind === 'asking' && phase.error && (
            <p className="message message--error" role="alert">
              {phase.error}
            </p>
          )}
        </form>
      )}
    </main>
  );
}

function deadlineIn(seconds: number | null): number | null {
  return seconds === null ? null : performance.now() + seconds * 1000;
}
