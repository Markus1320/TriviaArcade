// Typed client for the backend API. All game state lives on the server; the browser only
// keeps the run ID.

import type { Language } from '../strings';

export type QuestionFormat = 'free' | 'single' | 'multiple' | 'order';

export interface Question {
  question_id: number;
  number: number;
  text: string;
  // free: the player types the answer. single, multiple: the player picks from options.
  // order: the player taps every option in the correct order.
  format: QuestionFormat;
  // Empty for free questions.
  options: string[];
  streak: number;
  // 1UPs in stock and correct answers in a row towards the next one.
  lives: number;
  combo: number;
  // Correct answers in a row for a 1UP, and the most 1UPs a player can hold.
  life_combo: number;
  max_lives: number;
  // null when the server runs without a time limit.
  time_limit_seconds: number | null;
  // null until the question has been started (shown), see api.startQuestion.
  seconds_left: number | null;
}

export interface RunState {
  run_id: string;
  over: boolean;
  streak: number;
  lives: number;
  combo: number;
  open_question: Question | null;
  last_expected_answer: string | null;
  last_explanation: string | null;
  // Set when the run is over and the last question was a choice question. For order
  // questions both position lists are in order (correct order, tapped order).
  last_format: QuestionFormat | null;
  last_options: string[] | null;
  last_correct_options: number[] | null;
  last_selected_options: number[] | null;
  claimed_by: string | null;
}

export interface AnswerResult {
  correct: boolean;
  streak: number;
  game_over: boolean;
  // The answer came too late, or the time ran out without one.
  timed_out: boolean;
  lives: number;
  combo: number;
  // A correct answer completed the combo and earned a 1UP.
  life_earned: boolean;
  // A wrong or late answer cost a 1UP instead of ending the run.
  saved: boolean;
  // The question was skipped with a 1UP.
  skipped: boolean;
  // Set whenever the answer was not correct.
  expected_answer: string | null;
  // A sentence or two about the answer, shown after every verdict. null for old questions.
  explanation: string | null;
  // Choice questions: positions of the correct options (order questions: in the correct
  // order). null for free questions.
  correct_options: number[] | null;
}

export interface ClaimResult {
  handle: string;
  streak: number;
  // The player's leaderboard rank, based on their best run.
  rank: number;
  // Whether this run is the player's new best, i.e. their leaderboard entry.
  personal_best: boolean;
}

export interface LeaderboardRow {
  rank: number;
  handle: string;
  streak: number;
  finished_at: string;
}

// A question of a finished run in the public question log. It says whether the answer was
// right, never what was answered or by whom.
export interface LoggedQuestion {
  id: number;
  // Questions of one run share this and are shown as a group.
  run_ended_at: string;
  language: Language;
  number: number;
  correct: boolean;
  // Skipped with a 1UP: neither right nor wrong.
  skipped: boolean;
  format: QuestionFormat;
  question: string;
  // Choice questions: options in the shown order, correct_options as positions in it.
  options: string[];
  correct_options: number[];
  expected_answer: string;
  accepted_answers: string[];
  explanation: string | null;
  // The generator's notes before the question.
  notes: { topic?: string; candidates?: string[]; choice?: string; review?: string };
  model: string;
  // The user message sent to the generator.
  prompt: string;
}

export interface QuestionLogPage {
  questions: LoggedQuestion[];
  has_more: boolean;
}

// Error codes sent by the backend, see backend/app/api/errors.py.
export type ErrorCode =
  | 'run_not_found'
  | 'run_over'
  | 'no_open_question'
  | 'invalid_answer'
  | 'question_unavailable'
  | 'judge_unavailable'
  | 'no_life_left'
  | 'run_not_over'
  | 'run_already_claimed'
  | 'invalid_handle'
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode;

  constructor(status: number, code: ErrorCode, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

function errorFromBody(status: number, body: unknown): ApiError {
  if (typeof body === 'object' && body !== null) {
    const record = body as Record<string, unknown>;
    const code = typeof record.code === 'string' ? (record.code as ErrorCode) : 'unknown';
    const detail = typeof record.detail === 'string' ? record.detail : `HTTP ${String(status)}`;
    return new ApiError(status, code, detail);
  }
  return new ApiError(status, 'unknown', `HTTP ${String(status)}`);
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // Shown as strings.serverUnreachable, see errors.ts.
    throw new ApiError(0, 'unknown', 'The server is not reachable.');
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Empty or non JSON body; handled below.
  }
  if (!response.ok) {
    throw errorFromBody(response.status, payload);
  }
  // The shapes are defined by our own backend (see the Pydantic models in backend/app/api).
  return payload as T;
}

export const api = {
  // The questions of the run are written in this language until it ends.
  startRun: (language: Language) => request<{ run_id: string }>('POST', '/runs', { language }),
  getRun: (runId: string) => request<RunState>('GET', `/runs/${runId}`),
  nextQuestion: (runId: string) => request<Question>('POST', `/runs/${runId}/question`),
  // Starts the time limit when the question is shown. Safe to call again: the clock keeps running.
  startQuestion: (runId: string) => request<Question>('POST', `/runs/${runId}/question/start`),
  answer: (runId: string, answer: string) =>
    request<AnswerResult>('POST', `/runs/${runId}/answer`, { answer }),
  // Answers a choice question with the positions of the selected options.
  select: (runId: string, selected: number[]) =>
    request<AnswerResult>('POST', `/runs/${runId}/answer`, { selected }),
  // Spends a 1UP to skip the open question.
  skip: (runId: string) => request<AnswerResult>('POST', `/runs/${runId}/skip`),
  // Ends the run when the countdown ran out with nothing typed (a 1UP may save it).
  timeOut: (runId: string) => request<AnswerResult>('POST', `/runs/${runId}/timeout`),
  claim: (runId: string, handle: string) =>
    request<ClaimResult>('POST', `/runs/${runId}/claim`, { handle }),
  leaderboard: () => request<LeaderboardRow[]>('GET', '/leaderboard'),
  players: () => request<string[]>('GET', '/players'),
  // Ten questions per page, newest run first; the server shows at most the last 50.
  questionLog: (offset: number) =>
    request<QuestionLogPage>('GET', `/question-log?offset=${String(offset)}`),
};
