// Sound effects synthesized with the Web Audio API. No audio files, all sounds are original.
//
// A note is a square or sawtooth tone with a short volume envelope, which gives the
// typical chiptune character. The AudioContext is created lazily on the first sound after
// the player unmutes, because browsers only allow audio after a user gesture.

export type SoundName = 'start' | 'correct' | 'wrong' | 'gameOver';

interface Note {
  frequency: number; // Hz
  start: number; // seconds after the sound begins
  duration: number; // seconds
  type?: OscillatorType;
  // Optional pitch slide to this frequency over the note's duration.
  slideTo?: number;
}

const MASTER_VOLUME = 0.12;

// Frequencies of the notes used below (equal temperament, A4 = 440 Hz).
const C4 = 261.63;
const E4 = 329.63;
const G4 = 392.0;
const C5 = 523.25;
const E5 = 659.25;
const G5 = 783.99;
const C6 = 1046.5;
const B3 = 246.94;
const G3 = 196.0;
const E3 = 164.81;
const C3 = 130.81;

const SOUNDS: Record<SoundName, Note[]> = {
  // Short rising blip when a run starts.
  start: [
    { frequency: G4, start: 0, duration: 0.06 },
    { frequency: C5, start: 0.07, duration: 0.1 },
  ],
  // Quick major arpeggio.
  correct: [
    { frequency: C5, start: 0, duration: 0.07 },
    { frequency: E5, start: 0.07, duration: 0.07 },
    { frequency: G5, start: 0.14, duration: 0.07 },
    { frequency: C6, start: 0.21, duration: 0.16 },
  ],
  // Low falling buzz.
  wrong: [{ frequency: 220, start: 0, duration: 0.35, type: 'sawtooth', slideTo: 90 }],
  // Slow descending phrase that lands on a low note.
  gameOver: [
    { frequency: G4, start: 0.45, duration: 0.18 },
    { frequency: E4, start: 0.65, duration: 0.18 },
    { frequency: C4, start: 0.85, duration: 0.18 },
    { frequency: B3, start: 1.05, duration: 0.18 },
    { frequency: G3, start: 1.25, duration: 0.2 },
    { frequency: E3, start: 1.5, duration: 0.2 },
    { frequency: C3, start: 1.75, duration: 0.6, type: 'triangle' },
  ],
};

let context: AudioContext | null = null;

function audioContext(): AudioContext | null {
  if (typeof AudioContext === 'undefined') return null;
  context ??= new AudioContext();
  if (context.state === 'suspended') {
    void context.resume();
  }
  return context;
}

function playNote(ctx: AudioContext, note: Note, at: number): void {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  const start = at + note.start;
  const end = start + note.duration;

  oscillator.type = note.type ?? 'square';
  oscillator.frequency.setValueAtTime(note.frequency, start);
  if (note.slideTo !== undefined) {
    oscillator.frequency.exponentialRampToValueAtTime(note.slideTo, end);
  }
  // Fast attack, short release: avoids clicks at the start and end of each note.
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(MASTER_VOLUME, start + 0.005);
  gain.gain.setValueAtTime(MASTER_VOLUME, end - 0.02);
  gain.gain.linearRampToValueAtTime(0, end);

  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(end + 0.01);
}

export function playSound(name: SoundName): void {
  const ctx = audioContext();
  if (!ctx) return;
  const now = ctx.currentTime + 0.01;
  for (const note of SOUNDS[name]) {
    playNote(ctx, note, now);
  }
}

// Called when the player unmutes, inside the click handler, so the context may start.
export function unlockAudio(): void {
  audioContext();
}
