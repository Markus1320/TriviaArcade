import { useEffect, useState, type SubmitEvent } from 'react';

import { api, type ClaimResult } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

// Same rule as the backend (app/leaderboard/handles.py); the server has the final say.
const HANDLE_PATTERN = /^[A-Z0-9]{3,8}$/;

interface Props {
  runId: string;
  streak: number;
  onSaved: (result: ClaimResult) => void;
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
        onSaved(result);
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
    <main className="screen screen--handle">
      <h1 className="screen-title">{strings.enterHandle}</h1>
      <p className="score">
        <span className="score__label">{strings.finalStreak}</span>
        <span className="score__value">{strings.streakValue(streak)}</span>
      </p>
      <form className="handle-form" onSubmit={submit}>
        <label className="field-label" htmlFor="handle">
          {strings.handleHint}
        </label>
        <input
          id="handle"
          className="text-input text-input--handle"
          value={handle}
          onChange={(event) => {
            // Only letters and digits can be typed; the server validates again.
            setHandle(event.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase());
          }}
          maxLength={8}
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          autoFocus
          disabled={saving}
        />
        <button
          type="submit"
          className="button button--primary"
          disabled={saving || handle.trim() === ''}
        >
          {saving ? <span className="blink">{strings.saving}</span> : strings.save}
        </button>
      </form>
      {existing.length > 0 && (
        <section className="handle-picker">
          <p className="field-label">{strings.pickHandle}</p>
          <ul className="handle-list">
            {existing.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  className="chip"
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
        </section>
      )}
      {error && (
        <p className="message message--error" role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
