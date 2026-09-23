import { ApiError } from './api/client';
import { strings } from './strings';

// The backend sends short, player friendly messages; anything else gets a generic text.
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code !== 'unknown') return error.message;
  if (error instanceof ApiError && error.status === 0) return error.message;
  return strings.genericError;
}
