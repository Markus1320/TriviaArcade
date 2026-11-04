import { useEffect, useRef, useState, type SubmitEvent } from 'react';

import { type Question } from '../api/client';
import { useSound } from '../audio/soundState';
import { errorMessage } from '../errors';
import { useStrings } from '../language/languageState';
import { useCountdown } from '../useCountdown';
import { OptionList } from './OptionList';
import { TimeBar, URGENT_MS } from './TimeBar';

const MAX_ANSWER_LENGTH = 200;

interface Props {
  question: Question;
  // performance.now() timestamp when the time is up; null without a time limit.
  deadline: number | null;
  // The answer is on its way to the server: nothing can be changed.
  judging: boolean;
  // The last request failed; the question stays open.
  error: unknown;
  lives: number;
  // A typed answer (free questions).
  onAnswer: (answer: string) => void;
  // The picked option positions (choice questions; order questions in the tapped order).
  onSelect: (selected: number[]) => void;
  onSkip: () => void;
  // The time ran out with nothing typed or picked.
  onTimeout: () => void;
}

// The question while it is asked: time bar, question text, and the answer input or options
// with ENTER and SKIP. Keeps what the player typed or picked until it is sent.
export function AnswerForm(props: Props) {
  const { question, deadline, judging, error, lives } = props;
  const { play } = useSound();
  const strings = useStrings();
  const [answer, setAnswer] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const optionButtons = useRef<(HTMLButtonElement | null)[]>([]);

  const isChoice = question.format !== 'free';
  const ordered = question.format === 'order';
  // Something to send when the time is up. ENTER also needs every item of an order
  // question tapped.
  const hasAnswer = isChoice ? selected.length > 0 : answer.trim() !== '';
  const canSubmit = ordered ? selected.length === question.options.length : hasAnswer;

  // When the time is up (force) an incomplete order is sent too; it counts as wrong.
  const send = (force = false) => {
    if (judging || !(canSubmit || (force && hasAnswer))) return;
    if (isChoice) {
      props.onSelect(selected);
    } else {
      props.onAnswer(answer);
    }
  };

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    send();
  };

  const toggleOption = (index: number) => {
    // Order: a tap gives the next number, tapping a numbered item takes it back and the
    // later items move up. Multiple: a tap picks or unpicks. Single: a tap replaces.
    if (question.format === 'multiple' || ordered) {
      setSelected((current) =>
        current.includes(index) ? current.filter((item) => item !== index) : [...current, index],
      );
    } else {
      setSelected([index]);
    }
  };

  // Keyboard for choice questions: digits pick an option, the arrow keys move through the
  // options (and pick, when only one can be picked), Enter confirms. The listener is added
  // once; onKey always holds the version that sees the current state.
  const onKey = useRef<(event: KeyboardEvent) => void>(() => undefined);
  useEffect(() => {
    onKey.current = (event) => {
      if (judging || !isChoice || event.ctrlKey || event.metaKey || event.altKey) return;
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
        send();
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

  // Time is up: whatever the player typed or picked is sent; with nothing the run ends,
  // unless a 1UP saves it.
  const remainingMs = useCountdown(judging ? null : deadline, {
    onSecond: (secondsLeft) => {
      if (secondsLeft * 1000 <= URGENT_MS) play('tick');
    },
    onExpire: () => {
      if (judging) return;
      if (hasAnswer) {
        send(true);
      } else {
        props.onTimeout();
      }
    },
  });

  const limit = question.time_limit_seconds;
  return (
    <>
      {limit !== null && remainingMs !== null && (
        <TimeBar remainingMs={remainingMs} limitMs={limit * 1000} />
      )}
      <section className="question-box">
        <h2 className="question-text question-text--locked">{question.text}</h2>
      </section>
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
            onClick={props.onSkip}
            disabled={judging}
          >
            {strings.skipQuestion}
          </button>
        )}
        {error !== null && (
          <p className="message message--error" role="alert">
            {errorMessage(error, strings)}
          </p>
        )}
      </form>
    </>
  );
}
