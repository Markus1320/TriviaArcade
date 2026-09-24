import { useEffect, useState } from 'react';

import { api, type ClaimResult, type LeaderboardRow } from '../api/client';
import { errorMessage } from '../errors';
import { strings } from '../strings';

interface Props {
  highlight?: ClaimResult;
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
    <main className="screen screen--leaderboard">
      <h1 className="screen-title">{strings.leaderboard}</h1>
      {highlight && (
        <p className="message message--success" role="status">
          {highlight.personal_best
            ? strings.placed(highlight.handle, highlight.rank)
            : strings.notPersonalBest(highlight.handle, highlight.rank)}
        </p>
      )}
      {error && (
        <p className="message message--error" role="alert">
          {error}
        </p>
      )}
      {rows === null && !error && (
        <p className="loading">
          <span className="blink">...</span>
        </p>
      )}
      {rows?.length === 0 && <p className="message">{strings.leaderboardEmpty}</p>}
      {rows && rows.length > 0 && (
        <table className="scores">
          <thead>
            <tr>
              <th scope="col">{strings.rank}</th>
              <th scope="col">{strings.handle}</th>
              <th scope="col" className="scores__streak">
                {strings.score}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const classes = [`scores__row scores__row--rank-${String(Math.min(row.rank, 4))}`];
              if (highlight?.handle === row.handle) classes.push('scores__row--highlight');
              return (
                <tr key={row.handle} className={classes.join(' ')}>
                  <td>{strings.rankLabel(row.rank)}</td>
                  <td>{row.handle}</td>
                  <td className="scores__streak">{strings.streakValue(row.streak)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <button type="button" className="button button--primary" onClick={onBack} autoFocus>
        {highlight ? strings.playAgain : strings.backToTitle}
      </button>
    </main>
  );
}
