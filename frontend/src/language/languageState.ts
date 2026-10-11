import { createContext, useContext } from 'react';

import type { Language, Strings } from '../strings';

export interface LanguageState {
  language: Language;
  // The UI texts in the current language.
  strings: Strings;
  toggleLanguage: () => void;
}

export const LanguageContext = createContext<LanguageState | null>(null);

export function useLanguage(): LanguageState {
  const state = useContext(LanguageContext);
  if (!state) throw new Error('useLanguage must be used inside LanguageProvider');
  return state;
}

export function useStrings(): Strings {
  return useLanguage().strings;
}
