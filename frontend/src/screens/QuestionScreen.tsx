import { useCallback, useEffect, useRef, useState, type SubmitEvent } from 'react';

import { api, type AnswerResult, type Question } from '../api/client';
import { useSound } from '../audio/soundState';
import { LifeMeter } from '../components/LifeMeter';
import { OptionList, type ChoiceReveal } from '../components/OptionList';
import { TimeBar, URGENT_MS } from '../components/TimeBar';
import { errorMessage } from '../errors';
import { useStrings } from '../language/languageState';
import { useCountdown } from '../useCountdown';

const MAX_ANSWER_LENGTH = 200;

export interface GameOverResult {
  streak: number;
  expectedAnswer: string | null;
  explanation: string | null;
  timedOut: boolean;
  choice: ChoiceReveal | null;
}

interface Props {
  runId: string;
  onGameOver: (result: GameOverResult) => void;
}

// deadline: performance.now() timestamp when the time is up, null without a time limit.
type Phase =
  | { kind: 'loading' }
  | { kind: 'loadFailed'; error: unknown }
  | { kind: 'asking'; question: Question; error: unknown; deadline: number | null }
  | { kind: 'judging'; question: Question }
  // The run goes on: the answer was correct, a 1UP saved the run, or the question was skipped.
  | {
      kind: 'verdict';
      question: Question;
      result: AnswerResult;
      choice: ChoiceReveal | null;
    };

// The next question, requested while the player still sees the "correct" verdict.
interface Prefetch {
  promise: Promise<Question>;
  ready: Question | null;
}

export function QuestionScreen({ runId, onGameOver }: Props) {
  const { play } = useSound();
  const strings = useStrings();
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  // The typed answer of a free question, or the picked options of a choice question.
  const [answer, setAnswer] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const prefetch = useRef<Prefetch | null>(null);
  const optionButtons = useRef<(HTMLButtonElement | null)[]>([]);

  const fail = useCallback((err: unknown) => {
    setPhase({ kind: 'loadFailed', error: err });
  }, []);

  // Tells the server the open question is now shown, which starts its time limit, then shows
  // it. The response is the open question itself, so a prefetched copy is not needed here.
  // After a reload the clock keeps running, so seconds_left may already be low or zero.
  const showQuestion = useCallback(() => {
    api
      .startQuestion(runId)
      .then((started) => {
        setAnswer('');
        setSelected([]);
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

  const question = 'question' in phase ? phase.question : null;
  const isChoice = question !== null && question.format !== 'free';
  const ordered = question?.format === 'order';
  // Something to judge when the time is up. ENTER also needs every item of an order
  // question tapped.
  const hasAnswer = isChoice ? selected.length > 0 : answer.trim() !== '';
  const canSubmit = ordered ? selected.length === question.options.length : hasAnswer;

  const revealOf = (shown: Question, result: AnswerResult): ChoiceReveal | null =>
    result.correct_options === null
      ? null
      : {
          options: shown.options,
          correct: result.correct_options,
          // A skipped question was not answered, whatever was picked before.
          selected: result.skipped ? [] : selected,
          ordered: shown.format === 'order',
        };

  const endRun = (shown: Question, result: AnswerResult) => {
    play('wrong');
    play('gameOver');
    onGameOver({
      streak: result.streak,
      expectedAnswer: result.expected_answer,
      explanation: result.explanation,
      timedOut: result.timed_out,
      choice: revealOf(shown, result),
    });
  };

  // Shows what happened; unless the run is over, the next question is prepared meanwhile.
  const showResult = (shown: Question, result: AnswerResult) => {
    if (result.game_over) {
      endRun(shown, result);
      return;
    }
    if (result.correct) {
      play(result.life_earned ? 'oneUp' : 'correct');
    } else if (result.saved) {
      play('wrong');
    }
    setPhase({ kind: 'verdict', question: shown, result, choice: revealOf(shown, result) });
    startPrefetch();
  };

  // Sends the typed answer or the picked options, whichever the question asks for. When the
  // time is up (force) an incomplete order is sent too; it counts as wrong.
  const sendAnswer = (force = false) => {
    if (phase.kind !== 'asking' || !(canSubmit || (force && hasAnswer))) return;
    const shown = phase.question;
    setPhase({ kind: 'judging', question: shown });
    const request = isChoice ? api.select(runId, selected) : api.answer(runId, answer);
    request
      .then((result) => {
        showResult(shown, result);
      })
      .catch((err: unknown) => {
        // A judge failure pauses the run: the question stays open and can be answered again.
        // The server gives a fresh time limit for it.
        setPhase({
          kind: 'asking',
          question: shown,
          error: err,
          deadline: deadlineIn(shown.time_limit_seconds),
        });
      });
  };

  // Spends a 1UP on the open question. Errors (e.g. no 1UP left) keep the question open.
  const skipQuestion = () => {
    if (phase.kind !== 'asking') return;
    const shown = phase.question;
    setPhase({ kind: 'judging', question: shown });
    api
      .skip(runId)
      .then((result) => {
        showResult(shown, result);
      })
      .catch((err: unknown) => {
        setPhase({ kind: 'asking', question: shown, error: err, deadline: phase.deadline });
      });
  };

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    sendAnswer();
  };

  // Time is up: whatever the player typed or picked is sent; with nothing the run ends,
  // unless a 1UP saves it.
  const expire = () => {
    if (phase.kind !== 'asking') return;
    if (hasAnswer) {
      sendAnswer(true);
      return;
    }
    const shown = phase.question;
    setPhase({ kind: 'judging', question: shown });
    api
      .timeOut(runId)
      .then((result) => {
        showResult(shown, result);
      })
      .catch(fail);
  };

  const toggleOption = (index: number) => {
    // Order: a tap gives the next number, tapping a numbered item takes it back and the
    // later items move up.
    if (question?.format === 'multiple' || question?.format === 'order') {
      setSelected((current) =>
        current.includes(index) ? current.filter((item) => item !== index) : [...current, index],
      );
    } else {
      setSelected([index]);
    }
  };

  // Keyboard for choice questions: digits pick an option, the arrow keys move through the
  // options (and pick, when only one can be picked), Enter confirms.
  const asking = phase.kind === 'asking';
  const onKey = useRef<(event: KeyboardEvent) => void>(() => undefined);
  useEffect(() => {
    onKey.current = (event) => {
      if (!asking || !isChoice || event.ctrlKey || event.metaKey || event.altKey) return;
      const count = question.options.length;
      const digit = Number(event.key);
      if (Number.isInteger(digit) && digit >= 1 && digit <= count) {
        event.preventDefault();
        toggleOption(digit - 1);
        optionButtons.current[digit - 1]?.focus();
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        const focused = optionButtons.current.findIndex(
          (button) => button !== null && button === document.activeElement,
        );
        const start = focused === -1 ? (step === 1 ? -1 : 0) : focused;
        const next = (start + step + count) % count;
        optionButtons.current[next]?.focus();
        if (question.format === 'single') setSelected([next]);
      } else if (event.key === 'Enter') {
        // Enter on a focused option would pick it again instead of confirming.
        event.preventDefault();
        sendAnswer();
      }
    };
  });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      onKey.current(event);
    };
    window.addEventListener('keydown', listener);
    return () => {
      window.removeEventListener('keydown', listener);
    };
  }, []);

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
  if (phase.kind === 'loadFailed' || question === null) {
    return (
      <main className="screen screen--question">
        <p className="message message--error" role="alert">
          {phase.kind === 'loadFailed' ? errorMessage(phase.error, strings) : strings.genericError}
        </p>
        <button type="button" className="button button--primary" onClick={loadQuestion} autoFocus>
          {strings.retry}
        </button>
      </main>
    );
  }

  const verdict = phase.kind === 'verdict' ? phase.result : null;
  const correct = verdict?.correct === true;
  const streak = verdict ? verdict.streak : question.streak;
  const lives = verdict ? verdict.lives : question.lives;
  const combo = verdict ? verdict.combo : question.combo;
  const limit = question.time_limit_seconds;
  const judging = phase.kind === 'judging';
  return (
    <main className="screen screen--question">
      <header className="hud">
        <p className="hud__item">{strings.questionNumber(question.number)}</p>
        <LifeMeter
          lives={lives}
          combo={combo}
          lifeCombo={question.life_combo}
          maxLives={question.max_lives}
        />
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
      {verdict === null && limit !== null && remainingMs !== null && (
        <TimeBar remainingMs={remainingMs} limitMs={limit * 1000} />
      )}
      {/* After a verdict the box shows what there is to learn, not the question again. */}
      <section
        className={
          verdict === null
            ? 'question-box'
            : correct
              ? 'question-box question-box--correct'
              : 'question-box question-box--saved'
        }
      >
        {verdict?.explanation ? (
          <p className="question-text">{verdict.explanation}</p>
        ) : (
          <h2 className="question-text question-text--locked">{question.text}</h2>
        )}
      </section>
      {phase.kind === 'verdict' && verdict !== null ? (
        <>
          {phase.choice ? (
            <OptionList
              options={phase.choice.options}
              selected={phase.choice.selected}
              reveal={phase.choice}
            />
          ) : (
            !correct &&
            verdict.expected_answer !== null && (
              <p className="answer-reveal__value">
                {strings.correctAnswerWas}: {verdict.expected_answer}
              </p>
            )
          )}
          {correct ? (
            <p className="verdict verdict--correct" role="status">
              {strings.correct}
            </p>
          ) : (
            <p className="verdict verdict--saved" role="status">
              {verdict.skipped ? strings.skipped : strings.savedBy1up}
            </p>
          )}
          {verdict.life_earned && (
            <p className="one-up" role="status">
              {strings.oneUp}
            </p>
          )}
          <button type="button" className="button button--primary" onClick={loadQuestion} autoFocus>
            {strings.nextQuestion}
          </button>
        </>
      ) : (
        <form className="answer-form" onSubmit={submit}>
          {isChoice ? (
            <>
              <p className="field-label">
                {ordered
                  ? strings.tapInOrder
                  : question.format === 'multiple'
                    ? strings.pickAll
                    : strings.pickOne}
              </p>
              <OptionList
                options={question.options}
                selected={selected}
                multiple={question.format === 'multiple'}
                ordered={ordered}
                disabled={judging}
                onToggle={toggleOption}
                buttons={optionButtons}
              />
            </>
          ) : (
            <>
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
                // Typing only: pasting or dropping a looked up answer is blocked.
                onPaste={(event) => {
                  event.preventDefault();
                }}
                onDrop={(event) => {
                  event.preventDefault();
                }}
                // No autoFocus: on phones it opens the keyboard, which hides the question.
                disabled={judging}
              />
            </>
          )}
          <button type="submit" className="button button--primary" disabled={judging || !canSubmit}>
            {judging ? <span className="blink">{strings.judging}</span> : strings.submit}
          </button>
          {lives > 0 && (
            <button
              type="button"
              className="button button--secondary"
              onClick={skipQuestion}
              disabled={judging}
            >
              {strings.skipQuestion}
            </button>
          )}
          {phase.kind === 'asking' && phase.error !== null && (
            <p className="message message--error" role="alert">
              {errorMessage(phase.error, strings)}
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
