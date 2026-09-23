// All UI texts live here so a translation can be added later.
export const strings = {
  title: 'TRIVIA ARCADE',
  subtitle: 'Geography and history. One wrong answer ends the run.',
  start: 'START',
  showLeaderboard: 'LEADERBOARD',
  backToTitle: 'BACK TO TITLE',
  playAgain: 'PLAY AGAIN',

  loadingQuestion: 'Preparing your question...',
  questionNumber: (number: number) => `QUESTION ${String(number)}`,
  streak: (streak: number) => `STREAK ${String(streak)}`,
  answerLabel: 'Your answer',
  submit: 'SUBMIT',
  judging: 'Judging...',
  correct: 'CORRECT!',
  nextQuestion: 'NEXT QUESTION',
  retry: 'TRY AGAIN',

  gameOver: 'GAME OVER',
  finalStreak: (streak: number) => `Final streak: ${String(streak)}`,
  correctAnswerWas: 'The correct answer was',
  saveScore: 'SAVE SCORE',
  skip: 'SKIP',

  enterHandle: 'ENTER YOUR HANDLE',
  handleHint: '3 to 8 characters, letters A-Z and digits 0-9',
  handleInvalid: 'Use 3 to 8 letters (A-Z) or digits.',
  pickHandle: 'Or pick an existing handle:',
  saving: 'Saving...',
  save: 'SAVE',
  placed: (handle: string, rank: number) => `${handle} placed #${String(rank)}`,

  leaderboard: 'TOP 10',
  leaderboardEmpty: 'No scores yet. Be the first!',
  rank: 'RANK',
  handle: 'HANDLE',
  score: 'STREAK',

  genericError: 'Something went wrong. Please try again.',
} as const;
