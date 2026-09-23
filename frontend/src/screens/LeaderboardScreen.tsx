import { useEffect, useState } from 'react';

import { api, type LeaderboardRow } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

interface Props {
  highlight?: { handle: string; rank: number };
  onBack: () => void;
}

export function LeaderboardScreen({ highlight, onBack }: Props) {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .leaderboard()
      .then(setRows)
      .catch((err: unknown) => {
        setError(errorMessage(err));
      });
  }, []);

  return (
    <main className="screen">
      <h1>{strings.leaderboard}</h1>
      {highlight && <p>{strings.placed(highlight.handle, highlight.rank)}</p>}
      {error && <p role="alert">{error}</p>}
      {rows?.length === 0 && <p>{strings.leaderboardEmpty}</p>}
      {rows && rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{strings.rank}</th>
              <th>{strings.handle}</th>
              <th>{strings.score}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${String(row.rank)}-${row.handle}`}
                className={highlight?.rank === row.rank ? 'highlight' : undefined}
              >
                <td>{row.rank}</td>
                <td>{row.handle}</td>
                <td>{row.streak}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button type="button" onClick={onBack} autoFocus>
        {highlight ? strings.playAgain : strings.backToTitle}
      </button>
    </main>
  );
}
