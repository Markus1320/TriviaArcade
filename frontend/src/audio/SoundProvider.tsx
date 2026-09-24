import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { playSound, unlockAudio, type SoundName } from './sfx';
import { SoundContext } from './soundState';

// Sound is muted by default. The player's choice is remembered in this browser.
const STORAGE_KEY = 'triviaarcade.soundOn';

function loadPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function savePreference(soundOn: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(soundOn));
  } catch {
    // Ignored: the preference is a convenience.
  }
}

export function SoundProvider({ children }: { children: ReactNode }) {
  const [soundOn, setSoundOn] = useState(loadPreference);

  const toggleSound = useCallback(() => {
    setSoundOn((current) => {
      const next = !current;
      savePreference(next);
      if (next) unlockAudio();
      return next;
    });
  }, []);

  const play = useCallback(
    (name: SoundName) => {
      if (soundOn) playSound(name);
    },
    [soundOn],
  );

  const value = useMemo(() => ({ soundOn, toggleSound, play }), [soundOn, toggleSound, play]);
  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}
