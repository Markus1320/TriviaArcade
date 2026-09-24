import { createContext, useContext } from 'react';

import type { SoundName } from './sfx';

export interface SoundState {
  soundOn: boolean;
  toggleSound: () => void;
  play: (name: SoundName) => void;
}

export const SoundContext = createContext<SoundState | null>(null);

export function useSound(): SoundState {
  const state = useContext(SoundContext);
  if (!state) throw new Error('useSound must be used inside SoundProvider');
  return state;
}
