import { useState } from 'react';

import { api } from '../api/client';
import { useSound } from '../audio/soundState';
import { errorMessage } from '../errors';
import { useLanguage } from '../language/languageState';

interface Props {
  onStarted: (runId: string) => void;
  onShowLeaderboard: () => void;
}

export function TitleScreen({ onStarted, onShowLeaderboard }: Props) {
  const { play } = useSound();
  const { language, strings } = useLanguage();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const start = () => {
    play('start');
    setStarting(true);
    setError(null);
    api
      .startRun(language)
      .then(({ run_id }) => {
        onStarted(run_id);
      })
      .catch((err: unknown) => {
        setError(err);
        setStarting(false);
      });
  };

  return (
    <main className="screen screen--title">
      <h1 className="logo">
        <span className="logo__top">{strings.titleTop}</span>
        <span className="logo__bottom">{strings.titleBottom}</span>
      </h1>
      <p className="tagline">{strings.subtitle}</p>
      <button type="button" className="press-start" onClick={start} disabled={starting} autoFocus>
        <span className={starting ? undefined : 'blink'}>{strings.start}</span>
      </button>
      <p className="hint">{strings.rules}</p>
      <button type="button" className="button button--secondary" onClick={onShowLeaderboard}>
        {strings.showLeaderboard}
      </button>
      {error !== null && (
        <p className="message message--error" role="alert">
          {errorMessage(error, strings)}
        </p>
      )}
      <p className="footer">{strings.footer}</p>
    </main>
  );
}
