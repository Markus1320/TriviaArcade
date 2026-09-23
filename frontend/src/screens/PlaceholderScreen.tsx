import { useEffect, useState } from 'react';

import { fetchHealth, type HealthResponse } from '../api/client';
import { strings } from '../strings';

type HealthState =
  { kind: 'loading' } | { kind: 'loaded'; health: HealthResponse } | { kind: 'failed' };

function statusText(state: HealthState, key: keyof HealthResponse): string {
  switch (state.kind) {
    case 'loading':
      return strings.statusChecking;
    case 'failed':
      return strings.statusUnreachable;
    case 'loaded':
      return state.health[key] === 'ok' ? strings.statusOk : strings.statusError;
  }
}

export function PlaceholderScreen() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((result) => {
        setHealth({ kind: 'loaded', health: result });
      })
      .catch(() => {
        if (!controller.signal.aborted) setHealth({ kind: 'failed' });
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="placeholder">
      <h1>{strings.title}</h1>
      <p>{strings.comingSoon}</p>
      <dl>
        <dt>{strings.backendLabel}</dt>
        <dd>{statusText(health, 'status')}</dd>
        <dt>POSTGRES</dt>
        <dd>{statusText(health, 'postgres')}</dd>
        <dt>NEO4J</dt>
        <dd>{statusText(health, 'neo4j')}</dd>
      </dl>
    </main>
  );
}
