// Typed client for the backend API. All game state lives on the server; the browser only
// keeps the run ID.

export interface Question {
  question_id: number;
  number: number;
  text: string;
  streak: number;
  // null when the server runs without a time limit.
  time_limit_seconds: number | null;
  // null until the question has been started (shown), see api.startQuestion.
  seconds_left: number | null;
}

export interface RunState {
  run_id: string;
  over: boolean;
  streak: number;
  open_question: Question | null;
  last_expected_answer: string | null;
  last_explanation: string | null;
  claimed_by: string | null;
}

export interface AnswerResult {
  correct: boolean;
  streak: number;
  game_over: boolean;
  // The answer came too late, or the time ran out without one.
  timed_out: boolean;
  // Only set when the run is over.
  expected_answer: string | null;
  // A sentence or two about the answer, shown after every verdict. null for old questions.
  explanation: string | null;
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

// Error codes sent by the backend, see backend/app/api/errors.py.
export type ErrorCode =
  | 'run_not_found'
  | 'run_over'
  | 'no_open_question'
  | 'invalid_answer'
  | 'question_unavailable'
  | 'judge_unavailable'
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
  startRun: () => request<{ run_id: string }>('POST', '/runs'),
  getRun: (runId: string) => request<RunState>('GET', `/runs/${runId}`),
  nextQuestion: (runId: string) => request<Question>('POST', `/runs/${runId}/question`),
  // Starts the time limit when the question is shown. Safe to call again: the clock keeps running.
  startQuestion: (runId: string) => request<Question>('POST', `/runs/${runId}/question/start`),
  answer: (runId: string, answer: string) =>
    request<AnswerResult>('POST', `/runs/${runId}/answer`, { answer }),
  // Ends the run when the countdown ran out with nothing typed.
  timeOut: (runId: string) => request<AnswerResult>('POST', `/runs/${runId}/timeout`),
  claim: (runId: string, handle: string) =>
    request<ClaimResult>('POST', `/runs/${runId}/claim`, { handle }),
  leaderboard: () => request<LeaderboardRow[]>('GET', '/leaderboard'),
  players: () => request<string[]>('GET', '/players'),
};
