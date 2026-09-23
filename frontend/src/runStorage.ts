// Remembers the current run ID in this browser tab, so a reload can resume the run.
// Storage can be unavailable (private mode, blocked site data); the game still works.

const KEY = 'triviaarcade.runId';

export const runStorage = {
  get(): string | null {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(runId: string): void {
    try {
      sessionStorage.setItem(KEY, runId);
    } catch {
      // Ignored: resuming after a reload is a convenience.
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // Ignored, see above.
    }
  },
};
