import { useCallback, useEffect, useState } from 'react';

import { api, type ClaimResult } from './api/client';
import { type ChoiceReveal } from './components/OptionList';
import { runStorage } from './runStorage';
import { GameOverScreen } from './screens/GameOverScreen';
import { HandleScreen } from './screens/HandleScreen';
import { LeaderboardScreen } from './screens/LeaderboardScreen';
import { QuestionLogScreen } from './screens/QuestionLogScreen';
import { QuestionScreen } from './screens/QuestionScreen';
import { TitleScreen } from './screens/TitleScreen';

export type Screen =
  | { name: 'title' }
  | { name: 'question'; runId: string }
  | {
      name: 'gameOver';
      runId: string;
      streak: number;
      expectedAnswer: string | null;
      explanation: string | null;
      timedOut: boolean;
      // The options of the last question with what was right and what was picked.
      choice: ChoiceReveal | null;
    }
  | { name: 'handle'; runId: string; streak: number }
  | { name: 'leaderboard'; highlight?: ClaimResult }
  | { name: 'questionLog' };

export function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'title' });

  // Resume an unfinished or unsaved run after a page reload.
  useEffect(() => {
    const runId = runStorage.get();
    if (runId === null) return;
    api
      .getRun(runId)
      .then((run) => {
        if (!run.over) {
          setScreen({ name: 'question', runId });
        } else if (run.claimed_by === null) {
          setScreen({
            name: 'gameOver',
            runId,
            streak: run.streak,
            expectedAnswer: run.last_expected_answer,
            explanation: run.last_explanation,
            timedOut: false,
            choice:
              run.last_options && run.last_correct_options
                ? {
                    options: run.last_options,
                    correct: run.last_correct_options,
                    selected: run.last_selected_options ?? [],
                    ordered: run.last_format === 'order',
                  }
                : null,
          });
        } else {
          runStorage.clear();
        }
      })
      .catch(() => {
        runStorage.clear();
      });
  }, []);

  const toTitle = useCallback(() => {
    runStorage.clear();
    setScreen({ name: 'title' });
  }, []);

  switch (screen.name) {
    case 'title':
      return (
        <TitleScreen
          onStarted={(runId) => {
            runStorage.set(runId);
            setScreen({ name: 'question', runId });
          }}
          onShowLeaderboard={() => {
            setScreen({ name: 'leaderboard' });
          }}
          onShowQuestionLog={() => {
            setScreen({ name: 'questionLog' });
          }}
        />
      );
    case 'question':
      return (
        <QuestionScreen
          runId={screen.runId}
          onGameOver={(result) => {
            setScreen({ name: 'gameOver', runId: screen.runId, ...result });
          }}
        />
      );
    case 'gameOver':
      return (
        <GameOverScreen
          streak={screen.streak}
          expectedAnswer={screen.expectedAnswer}
          explanation={screen.explanation}
          timedOut={screen.timedOut}
          choice={screen.choice}
          onSave={() => {
            setScreen({ name: 'handle', runId: screen.runId, streak: screen.streak });
          }}
          onSkip={toTitle}
        />
      );
    case 'handle':
      return (
        <HandleScreen
          runId={screen.runId}
          streak={screen.streak}
          onSaved={(result) => {
            runStorage.clear();
            setScreen({ name: 'leaderboard', highlight: result });
          }}
        />
      );
    case 'leaderboard':
      return <LeaderboardScreen highlight={screen.highlight} onBack={toTitle} />;
    case 'questionLog':
      return <QuestionLogScreen onBack={toTitle} />;
  }
}
