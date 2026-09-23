// Typed client for the backend API. All game state lives on the server; the browser only
// keeps the run ID.

export interface Question {
  question_id: number;
  number: number;
  text: string;
  streak: number;
}

export interface RunState {
  run_id: string;
  over: boolean;
  streak: number;
  open_question: Question | null;
  last_expected_answer: string | null;
  claimed_by: string | null;
}

export interface AnswerResult {
  correct: boolean;
  streak: number;
  game_over: boolean;
  // Only set when the run is over.
  expected_answer: string | null;
}

export interface ClaimResult {
  handle: string;
  streak: number;
  rank: number;
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
  answer: (runId: string, answer: string) =>
    request<AnswerResult>('POST', `/runs/${runId}/answer`, { answer }),
  claim: (runId: string, handle: string) =>
    request<ClaimResult>('POST', `/runs/${runId}/claim`, { handle }),
  leaderboard: () => request<LeaderboardRow[]>('GET', '/leaderboard'),
  players: () => request<string[]>('GET', '/players'),
};
