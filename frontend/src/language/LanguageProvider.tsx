import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { LANGUAGES, STRINGS, type Language } from '../strings';
import { LanguageContext } from './languageState';

// The player's choice is remembered in this browser. Without one, a German browser starts
// in German and every other one in English.
const STORAGE_KEY = 'triviaarcade.language';

function isLanguage(value: string | null): value is Language {
  return value !== null && (LANGUAGES as readonly string[]).includes(value);
}

function loadPreference(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // Ignored: fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith('de') ? 'de' : 'en';
}

function savePreference(language: Language): void {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Ignored: the preference is a convenience.
  }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState(loadPreference);

  const toggleLanguage = useCallback(() => {
    setLanguage((current) => {
      const next = LANGUAGES[(LANGUAGES.indexOf(current) + 1) % LANGUAGES.length] ?? 'en';
      savePreference(next);
      return next;
    });
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({ language, strings: STRINGS[language], toggleLanguage }),
    [language, toggleLanguage],
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
