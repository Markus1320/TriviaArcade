import { type ReactNode, useCallback, useEffect, useState } from 'react';

import { api, type LoggedQuestion } from '../api/client';
import { errorMessage } from '../errors';
import { useStrings } from '../language/languageState';
import type { Strings } from '../strings';

interface Props {
  onBack: () => void;
}

interface RunGroup {
  endedAt: string;
  questions: LoggedQuestion[];
}

// The server sends the newest run first and its questions together, so a run is a stretch
// of consecutive questions with the same end time (possibly continued on the next page).
function groupByRun(questions: LoggedQuestion[]): RunGroup[] {
  const groups: RunGroup[] = [];
  for (const question of questions) {
    const last = groups.at(-1);
    if (last?.endedAt === question.run_ended_at) {
      last.questions.push(question);
    } else {
      groups.push({ endedAt: question.run_ended_at, questions: [question] });
    }
  }
  return groups;
}

export function QuestionLogScreen({ onBack }: Props) {
  const strings = useStrings();
  const [questions, setQuestions] = useState<LoggedQuestion[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Loading starts as true, so the first page needs no state change before the request.
  const load = useCallback((offset: number) => {
    api
      .questionLog(offset)
      .then((page) => {
        // A run finished in between shifts the pages; skip questions already shown.
        setQuestions((shown) => {
          const ids = new Set(shown.map((question) => question.id));
          return [...shown, ...page.questions.filter((question) => !ids.has(question.id))];
        });
        setHasMore(page.has_more);
      })
      .catch((err: unknown) => {
        setError(err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load(0);
  }, [load]);

  return (
    <main className="screen screen--log">
      <h1 className="screen-title">{strings.questionLog}</h1>
      <p className="hint">{strings.questionLogHint}</p>
      {!loading && error === null && questions.length === 0 && (
        <p className="message">{strings.questionLogEmpty}</p>
      )}
      {groupByRun(questions).map((group) => (
        <section key={group.endedAt} className="log-run">
          <h2 className="log-run__time">{strings.runEnded(new Date(group.endedAt))}</h2>
          <ul className="log-list">
            {group.questions.map((question) => (
              <li key={question.id}>
                <LogEntry question={question} strings={strings} />
              </li>
            ))}
          </ul>
        </section>
      ))}
      {error !== null && (
        <p className="message message--error" role="alert">
          {errorMessage(error, strings)}
        </p>
      )}
      {loading && (
        <p className="loading">
          <span className="blink">...</span>
        </p>
      )}
      {hasMore && !loading && (
        <button
          type="button"
          className="button button--secondary"
          onClick={() => {
            setLoading(true);
            setError(null);
            load(questions.length);
          }}
        >
          {strings.loadMore}
        </button>
      )}
      <button type="button" className="button button--primary" onClick={onBack}>
        {strings.backToTitle}
      </button>
    </main>
  );
}

function LogEntry({ question, strings }: { question: LoggedQuestion; strings: Strings }) {
  const { notes } = question;
  return (
    <details
      className={`log-entry log-entry--${question.correct ? 'right' : question.skipped ? 'skipped' : 'wrong'}`}
    >
      <summary className="log-entry__summary">
        <span
          className="log-entry__mark"
          role="img"
          aria-label={
            question.correct
              ? strings.answeredRight
              : question.skipped
                ? strings.answeredSkipped
                : strings.answeredWrong
          }
        >
          {question.correct ? '✓' : question.skipped ? '»' : '✗'}
        </span>
        <span className="log-entry__question">{question.question}</span>
      </summary>
      <dl className="log-detail">
        <Field label={strings.logFormat}>{strings.formatNames[question.format]}</Field>
        <Field label={strings.logLanguage}>{question.language.toUpperCase()}</Field>
        {question.format === 'order' ? (
          <Field label={strings.logOptions}>
            <ol className="log-detail__order">
              {question.correct_options.map((index) => (
                <li key={index}>{question.options[index]}</li>
              ))}
            </ol>
          </Field>
        ) : question.options.length > 0 ? (
          <Field label={strings.logOptions}>
            <ul className="log-detail__options">
              {question.options.map((option, index) => {
                const right = question.correct_options.includes(index);
                return (
                  <li key={option} className={right ? 'log-detail__option--right' : undefined}>
                    {right ? '✓ ' : '· '}
                    {option}
                  </li>
                );
              })}
            </ul>
          </Field>
        ) : (
          <>
            <Field label={strings.logAnswer}>{question.expected_answer}</Field>
            {question.accepted_answers.length > 0 && (
              <Field label={strings.logAccepted}>{question.accepted_answers.join(' · ')}</Field>
            )}
          </>
        )}
        {question.explanation && (
          <Field label={strings.logExplanation}>{question.explanation}</Field>
        )}
        {notes.topic && <Field label={strings.logTopic}>{notes.topic}</Field>}
        {notes.candidates && notes.candidates.length > 0 && (
          <Field label={strings.logCandidates}>
            <ol className="log-detail__candidates">
              {notes.candidates.map((candidate) => (
                <li key={candidate}>{candidate}</li>
              ))}
            </ol>
          </Field>
        )}
        {notes.choice && <Field label={strings.logChoice}>{notes.choice}</Field>}
        {notes.review && <Field label={strings.logReview}>{notes.review}</Field>}
        <Field label={strings.logModel}>{question.model}</Field>
        <Field label={strings.logPrompt}>
          <pre className="log-detail__prompt">{question.prompt}</pre>
        </Field>
      </dl>
    </details>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="log-detail__label">{label}</dt>
      <dd className="log-detail__value">{children}</dd>
    </>
  );
}
