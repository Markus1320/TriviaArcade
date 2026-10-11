import { useSound } from '../audio/soundState';
import { useStrings } from '../language/languageState';

export function SoundToggle() {
  const strings = useStrings();
  const { soundOn, toggleSound } = useSound();
  return (
    <button
      type="button"
      className="toggle toggle--sound"
      onClick={toggleSound}
      aria-pressed={soundOn}
      aria-label={soundOn ? strings.soundOnLabel : strings.soundOffLabel}
    >
      {soundOn ? strings.soundOn : strings.soundOff}
    </button>
  );
}
