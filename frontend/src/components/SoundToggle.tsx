import { useSound } from '../audio/soundState';
import { strings } from '../strings';

export function SoundToggle() {
  const { soundOn, toggleSound } = useSound();
  return (
    <button
      type="button"
      className="sound-toggle"
      onClick={toggleSound}
      aria-pressed={soundOn}
      aria-label={soundOn ? strings.soundOnLabel : strings.soundOffLabel}
    >
      {soundOn ? strings.soundOn : strings.soundOff}
    </button>
  );
}
