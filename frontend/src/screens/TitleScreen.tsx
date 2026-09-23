import { useState } from 'react';

import { api } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

interface Props {
  onStarted: (runId: string) => void;
  onShowLeaderboard: () => void;
}

export function TitleScreen({ onStarted, onShowLeaderboard }: Props) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setStarting(true);
    setError(null);
    api
      .startRun()
      .then(({ run_id }) => {
        onStarted(run_id);
      })
      .catch((err: unknown) => {
        setError(errorMessage(err));
        setStarting(false);
      });
  };

  return (
    <main className="screen">
      <h1>{strings.title}</h1>
      <p>{strings.subtitle}</p>
      <button type="button" onClick={start} disabled={starting} autoFocus>
        {strings.start}
      </button>
      <button type="button" onClick={onShowLeaderboard}>
        {strings.showLeaderboard}
      </button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
