import { useCallback, useEffect, useState } from 'react';

import { api, ApiError, type AnswerResult, type Question } from '../api/client';
import { useSound } from '../audio/soundState';
import { AnswerForm } from '../components/AnswerForm';
import { Hud } from '../components/Hud';
import { type ChoiceReveal } from '../components/OptionList';
import { Verdict } from '../components/Verdict';
import { errorMessage } from '../errors';
import { useStrings } from '../language/languageState';

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
  // Leaves the run, e.g. when there are no questions in its language.
  onQuit: () => void;
}

// What the screen shows: a question being loaded, an error, the open question, or the
// verdict on the last answer (while the run goes on).
type Phase =
  | { kind: 'loading' }
  | { kind: 'failed'; error: unknown }
  | {
      kind: 'asking';
      question: Question;
      // performance.now() timestamp when the time is up; null without a time limit.
      deadline: number | null;
      judging: boolean;
      error: unknown;
    }
  | { kind: 'verdict'; question: Question; result: AnswerResult; choice: ChoiceReveal | null };

// One question of a run, from loading it to the verdict. Talks to the server; the parts
// on screen are Hud, AnswerForm and Verdict.
export function QuestionScreen({ runId, onGameOver, onQuit }: Props) {
  const { play } = useSound();
  const strings = useStrings();
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });

  // Gets the open question (the server creates one if there is none), then tells the
  // server it is shown, which starts its clock. After a reload the clock keeps running,
  // so seconds_left may already be low or zero.
  const fetchQuestion = useCallback(() => {
    api
      .nextQuestion(runId)
      .then(() => api.startQuestion(runId))
      .then((question) => {
        setPhase({
          kind: 'asking',
          question,
          deadline: deadlineIn(question.seconds_left),
          judging: false,
          error: null,
        });
      })
      .catch((error: unknown) => {
        setPhase({ kind: 'failed', error });
      });
  }, [runId]);

  useEffect(() => {
    fetchQuestion();
  }, [fetchQuestion]);

  const loadNext = () => {
    setPhase({ kind: 'loading' });
    fetchQuestion();
  };

  // Shows what happened, or ends the run.
  const showResult = (question: Question, result: AnswerResult, selected: number[]) => {
    const choice =
      result.correct_options === null
        ? null
        : {
            options: question.options,
            correct: result.correct_options,
            selected,
            ordered: question.format === 'order',
          };
    if (result.game_over) {
      play('wrong');
      play('gameOver');
      onGameOver({
        streak: result.streak,
        expectedAnswer: result.expected_answer,
        explanation: result.explanation,
        timedOut: result.timed_out,
        choice,
      });
      return;
    }
    if (result.correct) {
      play(result.life_earned ? 'oneUp' : 'correct');
    } else if (result.saved) {
      // A skip makes no sound.
      play('wrong');
    }
    setPhase({ kind: 'verdict', question, result, choice });
  };

  // Sends an answer, a skip or a timeout. On an error the question stays open with the
  // message; once its time is up, the error screen offers TRY AGAIN instead.
  const send = (request: () => Promise<AnswerResult>, selected: number[]) => {
    if (phase.kind !== 'asking' || phase.judging) return;
    const asking = phase;
    setPhase({ ...asking, judging: true, error: null });
    request()
      .then((result) => {
        showResult(asking.question, result, selected);
      })
      .catch((error: unknown) => {
        const timeIsUp = asking.deadline !== null && performance.now() >= asking.deadline;
        setPhase(timeIsUp ? { kind: 'failed', error } : { ...asking, error });
      });
  };

  if (phase.kind === 'loading') {
    return (
      <main className="screen screen--question">
        <p className="loading">
          <span className="blink">{strings.loadingQuestion}</span>
        </p>
      </main>
    );
  }

  if (phase.kind === 'failed') {
    // Trying again cannot help when the language has no questions at all.
    const hopeless =
      phase.error instanceof ApiError && phase.error.code === 'no_questions_in_language';
    return (
      <main className="screen screen--question">
        <p className="message message--error" role="alert">
          {errorMessage(phase.error, strings)}
        </p>
        {!hopeless && (
          <button type="button" className="button button--primary" onClick={loadNext} autoFocus>
            {strings.retry}
          </button>
        )}
        <button
          type="button"
          className={hopeless ? 'button button--primary' : 'button button--secondary'}
          onClick={onQuit}
          autoFocus={hopeless}
        >
          {strings.backToTitle}
        </button>
      </main>
    );
  }

  const { question } = phase;
  // After a verdict the HUD shows the run as it is now.
  const now = phase.kind === 'verdict' ? phase.result : question;
  return (
    <main className="screen screen--question">
      <Hud
        number={question.number}
        streak={now.streak}
        lives={now.lives}
        combo={now.combo}
        lifeCombo={question.life_combo}
        maxLives={question.max_lives}
        scored={phase.kind === 'verdict' && phase.result.correct}
      />
      {phase.kind === 'verdict' ? (
        <Verdict
          question={question}
          result={phase.result}
          choice={phase.choice}
          onNext={loadNext}
        />
      ) : (
        <AnswerForm
          // A new key for every question starts the form empty.
          key={question.question_id}
          question={question}
          deadline={phase.deadline}
          judging={phase.judging}
          error={phase.error}
          lives={question.lives}
          onAnswer={(answer) => {
            send(() => api.answer(runId, answer), []);
          }}
          onSelect={(selected) => {
            send(() => api.select(runId, selected), selected);
          }}
          onSkip={() => {
            // A skipped question was not answered, whatever was picked before.
            send(() => api.skip(runId), []);
          }}
          onTimeout={() => {
            send(() => api.timeOut(runId), []);
          }}
        />
      )}
    </main>
  );
}

function deadlineIn(seconds: number | null): number | null {
  return seconds === null ? null : performance.now() + seconds * 1000;
}
