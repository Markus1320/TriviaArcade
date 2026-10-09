import { strings } from '../strings';

// Below this many milliseconds the bar turns red and the countdown ticks.
export const URGENT_MS = 5000;

interface Props {
  remainingMs: number;
  limitMs: number;
}

// A shrinking bar for the time left. The width is set from JavaScript rather than with a CSS
// transition, so it also works when the player prefers reduced motion.
export function TimeBar({ remainingMs, limitMs }: Props) {
  const share = limitMs > 0 ? Math.min(1, remainingMs / limitMs) : 0;
  const urgent = remainingMs <= URGENT_MS;
  return (
    <div
      className={urgent ? 'time-bar time-bar--urgent' : 'time-bar'}
      role="progressbar"
      aria-label={strings.timeLeftLabel}
      aria-valuemin={0}
      aria-valuemax={Math.round(limitMs / 1000)}
      aria-valuenow={Math.ceil(remainingMs / 1000)}
    >
      <div className="time-bar__fill" style={{ width: `${String(share * 100)}%` }} />
    </div>
  );
}
