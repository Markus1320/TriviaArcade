// All UI texts live here so a translation can be added later.

function pad(value: number, digits: number): string {
  return String(value).padStart(digits, '0');
}

function ordinal(rank: number): string {
  const tens = rank % 100;
  if (tens >= 11 && tens <= 13) return `${String(rank)}TH`;
  const suffixes: Record<number, string> = { 1: 'ST', 2: 'ND', 3: 'RD' };
  return `${String(rank)}${suffixes[rank % 10] ?? 'TH'}`;
}

export const strings = {
  titleTop: 'TRIVIA',
  titleBottom: 'ARCADE',
  subtitle: 'GEOGRAPHY & HISTORY',
  rules: 'ONE WRONG ANSWER ENDS THE RUN',
  start: 'PRESS START',
  showLeaderboard: 'HIGH SCORES',
  backToTitle: 'BACK',
  playAgain: 'PLAY AGAIN',
  footer: 'FACTS FROM WIKIDATA',

  soundOn: '♪ ON',
  soundOff: '♪ OFF',
  soundOnLabel: 'Sound is on. Turn sound off.',
  soundOffLabel: 'Sound is off. Turn sound on.',

  loadingQuestion: 'LOADING QUESTION',
  questionNumber: (number: number) => `QUESTION ${pad(number, 2)}`,
  streakLabel: 'STREAK',
  streakValue: (streak: number) => pad(streak, 3),
  answerLabel: 'YOUR ANSWER',
  answerPlaceholder: 'TYPE HERE',
  submit: 'ENTER',
  judging: 'JUDGING',
  correct: 'CORRECT!',
  nextQuestion: 'NEXT QUESTION',
  retry: 'TRY AGAIN',

  gameOver: 'GAME OVER',
  finalStreak: 'FINAL STREAK',
  correctAnswerWas: 'THE ANSWER WAS',
  saveScore: 'SAVE SCORE',
  skip: 'SKIP',

  enterHandle: 'ENTER YOUR NAME',
  handleHint: '3-8 LETTERS OR DIGITS',
  handleInvalid: 'USE 3 TO 8 LETTERS (A-Z) OR DIGITS',
  pickHandle: 'OR PICK YOUR NAME',
  saving: 'SAVING',
  save: 'SAVE',
  placed: (handle: string, rank: number) => `${handle} RANKS ${ordinal(rank)}!`,
  notPersonalBest: (handle: string, rank: number) =>
    `NO NEW BEST. ${handle} STAYS ${ordinal(rank)}.`,

  leaderboard: 'HIGH SCORES',
  leaderboardEmpty: 'NO SCORES YET. BE THE FIRST!',
  rank: 'RANK',
  handle: 'NAME',
  score: 'STREAK',
  rankLabel: ordinal,

  genericError: 'SOMETHING WENT WRONG. PLEASE TRY AGAIN.',
} as const;
