import { ApiError } from './api/client';
import type { Strings } from './strings';

// Errors are kept as they were thrown and turned into text when shown, so the message
// follows the language. The backend sends short, player friendly English messages; other
// languages translate them by error code. Anything else gets a generic text.
export function errorMessage(error: unknown, strings: Strings): string {
  if (error instanceof ApiError && error.code !== 'unknown') {
    return strings.errors[error.code] ?? error.message;
  }
  if (error instanceof ApiError && error.status === 0) return strings.serverUnreachable;
  return strings.genericError;
}
