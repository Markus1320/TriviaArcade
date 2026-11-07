import { type AnswerResult, type Question } from '../api/client';
import { useStrings } from '../language/languageState';
import { OptionList, type ChoiceReveal } from './OptionList';

interface Props {
  question: Question;
  result: AnswerResult;
  // Choice questions: the options marked right, missed and wrong.
  choice: ChoiceReveal | null;
  onNext: () => void;
}

// What the player sees after an answer while the run goes on: the answer was correct, a
// 1UP saved the run, or the question was skipped.
export function Verdict({ question, result, choice, onNext }: Props) {
  const strings = useStrings();
  const correct = result.correct;
  return (
    <>
      {/* The box now shows what there is to learn, not the question again. */}
      <section
        className={
          correct ? 'question-box question-box--correct' : 'question-box question-box--saved'
        }
      >
        {result.explanation ? (
          <p className="question-text">{result.explanation}</p>
        ) : (
          <h2 className="question-text question-text--locked">{question.text}</h2>
        )}
      </section>
      {choice ? (
        <OptionList options={choice.options} selected={choice.selected} reveal={choice} />
      ) : (
        !correct &&
        result.expected_answer !== null && (
          <p className="answer-reveal__value">
            {strings.correctAnswerWas}: {result.expected_answer}
          </p>
        )
      )}
      {correct ? (
        <p className="verdict verdict--correct" role="status">
          {strings.correct}
        </p>
      ) : (
        <p className="verdict verdict--saved" role="status">
          {result.skipped ? strings.skipped : strings.savedBy1up}
        </p>
      )}
      {result.life_earned && (
        <p className="one-up" role="status">
          {strings.oneUp}
        </p>
      )}
      <button type="button" className="button button--primary" onClick={onNext} autoFocus>
        {strings.nextQuestion}
      </button>
    </>
  );
}
