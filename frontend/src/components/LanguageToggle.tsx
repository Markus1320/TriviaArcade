import { useLanguage } from '../language/languageState';

// Switches the UI at once. Questions follow with the next run: a run keeps the language it
// was started in.
export function LanguageToggle() {
  const { strings, toggleLanguage } = useLanguage();
  return (
    <button
      type="button"
      className="toggle"
      onClick={toggleLanguage}
      aria-label={strings.languageLabel}
    >
      {strings.languageName}
    </button>
  );
}
