import { useEffect, useState, type SubmitEvent } from 'react';

import { api } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

// Same rule as the backend (app/leaderboard/handles.py); the server has the final say.
const HANDLE_PATTERN = /^[A-Z0-9]{3,8}$/;

interface Props {
  runId: string;
  streak: number;
  onSaved: (handle: string, rank: number) => void;
}

export function HandleScreen({ runId, streak, onSaved }: Props) {
  const [handle, setHandle] = useState('');
  const [existing, setExisting] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .players()
      .then(setExisting)
      .catch(() => {
        setExisting([]);
      });
  }, []);

  const save = (value: string) => {
    const normalized = value.trim().toUpperCase();
    if (!HANDLE_PATTERN.test(normalized)) {
      setError(strings.handleInvalid);
      return;
    }
    setSaving(true);
    setError(null);
    api
      .claim(runId, normalized)
      .then((result) => {
        onSaved(result.handle, result.rank);
      })
      .catch((err: unknown) => {
        setError(errorMessage(err));
        setSaving(false);
      });
  };

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    save(handle);
  };

  return (
    <main className="screen">
      <h1>{strings.enterHandle}</h1>
      <p>{strings.finalStreak(streak)}</p>
      <form onSubmit={submit}>
        <label htmlFor="handle">{strings.handleHint}</label>
        <input
          id="handle"
          value={handle}
          onChange={(event) => {
            setHandle(event.target.value.toUpperCase());
          }}
          maxLength={8}
          autoCapitalize="characters"
          autoComplete="off"
          autoFocus
          disabled={saving}
        />
        <button type="submit" disabled={saving || handle.trim() === ''}>
          {saving ? strings.saving : strings.save}
        </button>
      </form>
      {existing.length > 0 && (
        <>
          <p>{strings.pickHandle}</p>
          <ul className="handle-list">
            {existing.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => {
                    save(name);
                  }}
                >
                  {name}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
