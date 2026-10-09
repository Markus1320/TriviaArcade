import { useLayoutEffect, useRef, useState } from 'react';

const UPDATE_INTERVAL_MS = 100;

interface Callbacks {
  // Called once per whole second left (…, 3, 2, 1), not for 0.
  onSecond: (secondsLeft: number) => void;
  onExpire: () => void;
}

/**
 * Counts down to a deadline (a performance.now() timestamp) and returns the milliseconds left.
 * A null deadline pauses the countdown and keeps the last value. The callbacks may change on
 * every render; the latest ones are used.
 */
export function useCountdown(deadline: number | null, callbacks: Callbacks): number | null {
  const [remaining, setRemaining] = useState<number | null>(null);
  const latest = useRef(callbacks);

  // Declared first, so the countdown effect below already sees this render's callbacks.
  useLayoutEffect(() => {
    latest.current = callbacks;
  });

  // A layout effect, so a new deadline replaces the old value before the browser paints.
  useLayoutEffect(() => {
    if (deadline === null) return;
    let lastSecond: number | null = null;
    const update = () => {
      const left = Math.max(0, deadline - performance.now());
      setRemaining(left);
      const second = Math.ceil(left / 1000);
      if (second !== lastSecond && second > 0) {
        latest.current.onSecond(second);
      }
      lastSecond = second;
      if (left === 0) {
        window.clearInterval(timer);
        latest.current.onExpire();
      }
    };
    const timer = window.setInterval(update, UPDATE_INTERVAL_MS);
    update();
    return () => {
      window.clearInterval(timer);
    };
  }, [deadline]);

  return remaining;
}
