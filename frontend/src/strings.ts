// All UI texts live here, once per language. Arcade phrases (PRESS START, GAME OVER, HIGH
// SCORES, ENTER) and the name of the game are the same in every language.

import type { ErrorCode } from './api/client';

export type Language = 'en' | 'de';

export const LANGUAGES: readonly Language[] = ['en', 'de'];

function pad(value: number, digits: number): string {
  return String(value).padStart(digits, '0');
}

function ordinal(rank: number): string {
  const tens = rank % 100;
  if (tens >= 11 && tens <= 13) return `${String(rank)}TH`;
  const suffixes: Record<number, string> = { 1: 'ST', 2: 'ND', 3: 'RD' };
  return `${String(rank)}${suffixes[rank % 10] ?? 'TH'}`;
}

const shared = {
  titleTop: 'TRIVIA',
  titleBottom: 'ARCADE',
  start: 'PRESS START',
  showLeaderboard: 'HIGH SCORES',
  leaderboard: 'HIGH SCORES',
  gameOver: 'GAME OVER',
  oneUp: '1UP!',
  submit: 'ENTER',
  soundOn: '♪ ON',
  soundOff: '♪ OFF',
  streakValue: (streak: number) => pad(streak, 3),
};

const en = {
  ...shared,
  subtitle: 'GENERAL KNOWLEDGE',
  rules: 'ONE WRONG ANSWER ENDS THE RUN',
  backToTitle: 'BACK',
  playAgain: 'PLAY AGAIN',
  footer: 'FACTS FROM WIKIDATA',

  soundOnLabel: 'Sound is on. Turn sound off.',
  soundOffLabel: 'Sound is off. Turn sound on.',
  // The button shows the current language; pressing it switches to the other one.
  languageName: 'EN',
  languageLabel: 'Language: English. Switch to German.',

  loadingQuestion: 'LOADING QUESTION',
  questionNumber: (number: number) => `QUESTION ${pad(number, 2)}`,
  streakLabel: 'SCORE',
  answerLabel: 'YOUR ANSWER',
  answerPlaceholder: 'TYPE HERE',
  pickOne: 'PICK ONE',
  pickAll: 'SELECT ALL THAT APPLY',
  tapInOrder: 'TAP THEM IN THE RIGHT ORDER',
  // An item of an order question that the player put in another place.
  yourPlace: (place: number) => `YOU: ${String(place)}`,
  optionRight: 'RIGHT',
  // A correct option the player did not pick.
  optionMissed: 'MISSING',
  optionWrong: 'WRONG',
  judging: 'JUDGING',
  correct: 'CORRECT!',
  skipQuestion: 'SKIP (1UP)',
  skipped: 'SKIPPED',
  savedBy1up: 'SAVED BY 1UP!',
  livesFull: '1UPS FULL',
  comboToNext: (left: number) => `${String(left)} MORE FOR 1UP`,
  lifeMeterLabel: (lives: number, combo: number) =>
    `${String(lives)} 1UP. ${String(combo)} of 5 correct answers in a row towards the next.`,
  nextQuestion: 'NEXT QUESTION',
  retry: 'TRY AGAIN',
  timeLeftLabel: 'TIME LEFT',

  timeUp: 'TIME UP!',
  finalStreak: 'FINAL STREAK',
  correctAnswerWas: 'THE ANSWER WAS',
  correctOptionsWere: 'THE RIGHT CHOICE WAS',
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

  leaderboardEmpty: 'NO SCORES YET. BE THE FIRST!',
  rank: 'RANK',
  handle: 'NAME',
  score: 'SCORE',
  rankLabel: ordinal,

  showQuestionLog: 'QUESTION LOG',
  questionLog: 'QUESTION LOG',
  questionLogHint: 'QUESTIONS OF THE LAST FINISHED GAMES. TAP ONE FOR DETAILS.',
  questionLogEmpty: 'NO FINISHED GAMES YET.',
  loadMore: 'LOAD MORE',
  runEnded: (date: Date) =>
    date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).toUpperCase(),
  answeredRight: 'Answered correctly',
  answeredWrong: 'Answered wrongly',
  answeredSkipped: 'Skipped with a 1UP',
  logFormat: 'FORMAT',
  formatNames: {
    free: 'TYPED ANSWER',
    single: 'PICK ONE',
    multiple: 'SELECT ALL THAT APPLY',
    order: 'SORTING',
  },
  logOptions: 'OPTIONS',
  logAnswer: 'ANSWER',
  logAccepted: 'ALSO ACCEPTED',
  logExplanation: 'EXPLANATION',
  logTopic: 'TOPIC',
  logCandidates: 'CANDIDATES',
  logChoice: 'CHOICE',
  logReview: 'REVIEW',
  logModel: 'MODEL',
  logPrompt: 'PROMPT',
  logLanguage: 'LANGUAGE',

  genericError: 'SOMETHING WENT WRONG. PLEASE TRY AGAIN.',
  serverUnreachable: 'The server is not reachable.',
  // Texts for the error codes of the backend. Without an entry the backend's own (English)
  // message is shown.
  errors: {} as Partial<Record<ErrorCode, string>>,
};

export type Strings = typeof en;

const de: Strings = {
  ...shared,
  subtitle: 'ALLGEMEINWISSEN',
  rules: 'EINE FALSCHE ANTWORT BEENDET DAS SPIEL',
  backToTitle: 'ZURÜCK',
  playAgain: 'NOCHMAL SPIELEN',
  footer: 'FAKTEN VON WIKIDATA',

  soundOnLabel: 'Ton ist an. Ton ausschalten.',
  soundOffLabel: 'Ton ist aus. Ton einschalten.',
  languageName: 'DE',
  languageLabel: 'Sprache: Deutsch. Zu Englisch wechseln.',

  loadingQuestion: 'FRAGE WIRD GELADEN',
  questionNumber: (number: number) => `FRAGE ${pad(number, 2)}`,
  streakLabel: 'PUNKTE',
  answerLabel: 'DEINE ANTWORT',
  answerPlaceholder: 'HIER TIPPEN',
  pickOne: 'WÄHLE EINE ANTWORT',
  pickAll: 'WÄHLE ALLE RICHTIGEN',
  tapInOrder: 'TIPPE SIE IN DER RICHTIGEN REIHENFOLGE AN',
  yourPlace: (place: number) => `DU: ${String(place)}`,
  optionRight: 'RICHTIG',
  optionMissed: 'FEHLT',
  optionWrong: 'FALSCH',
  judging: 'PRÜFE',
  correct: 'RICHTIG!',
  skipQuestion: 'ÜBERSPRINGEN (1UP)',
  skipped: 'ÜBERSPRUNGEN',
  savedBy1up: 'GERETTET DURCH 1UP!',
  livesFull: '1UPS VOLL',
  comboToNext: (left: number) => `NOCH ${String(left)} BIS 1UP`,
  lifeMeterLabel: (lives: number, combo: number) =>
    `${String(lives)} 1UP. ${String(combo)} von 5 richtigen Antworten in Folge bis zum nächsten.`,
  nextQuestion: 'NÄCHSTE FRAGE',
  retry: 'NOCHMAL',
  timeLeftLabel: 'VERBLEIBENDE ZEIT',

  timeUp: 'ZEIT UM!',
  finalStreak: 'ENDSTAND',
  correctAnswerWas: 'DIE ANTWORT WAR',
  correctOptionsWere: 'RICHTIG WAR',
  saveScore: 'SPEICHERN',
  skip: 'ÜBERSPRINGEN',

  enterHandle: 'DEIN NAME',
  handleHint: '3-8 BUCHSTABEN ODER ZIFFERN',
  handleInvalid: '3 BIS 8 BUCHSTABEN (A-Z) ODER ZIFFERN',
  pickHandle: 'ODER WÄHLE DEINEN NAMEN',
  saving: 'SPEICHERE',
  save: 'SPEICHERN',
  placed: (handle: string, rank: number) => `${handle} IST AUF PLATZ ${String(rank)}!`,
  notPersonalBest: (handle: string, rank: number) =>
    `KEINE NEUE BESTLEISTUNG. ${handle} BLEIBT AUF PLATZ ${String(rank)}.`,

  leaderboardEmpty: 'NOCH KEINE EINTRÄGE. MACH DEN ANFANG!',
  rank: 'PLATZ',
  handle: 'NAME',
  score: 'PUNKTE',
  rankLabel: (rank: number) => `${String(rank)}.`,

  showQuestionLog: 'LETZTE FRAGEN',
  questionLog: 'LETZTE FRAGEN',
  questionLogHint: 'FRAGEN DER LETZTEN BEENDETEN SPIELE. TIPPE EINE FÜR DETAILS AN.',
  questionLogEmpty: 'NOCH KEINE BEENDETEN SPIELE.',
  loadMore: 'MEHR LADEN',
  runEnded: (date: Date) =>
    date.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }).toUpperCase(),
  answeredRight: 'Richtig beantwortet',
  answeredWrong: 'Falsch beantwortet',
  answeredSkipped: 'Mit einem 1UP übersprungen',
  logFormat: 'FORMAT',
  formatNames: {
    free: 'FREIE ANTWORT',
    single: 'EINE AUSWÄHLEN',
    multiple: 'ALLE RICHTIGEN WÄHLEN',
    order: 'SORTIEREN',
  },
  logOptions: 'OPTIONEN',
  logAnswer: 'ANTWORT',
  logAccepted: 'AUCH RICHTIG',
  logExplanation: 'ERKLÄRUNG',
  logTopic: 'THEMA',
  logCandidates: 'KANDIDATEN',
  logChoice: 'WAHL',
  logReview: 'PRÜFUNG',
  logModel: 'MODELL',
  logPrompt: 'PROMPT',
  logLanguage: 'SPRACHE',

  genericError: 'ETWAS IST SCHIEFGELAUFEN. BITTE NOCHMAL VERSUCHEN.',
  serverUnreachable: 'Der Server ist nicht erreichbar.',
  errors: {
    run_not_found: 'Dieses Spiel gibt es nicht.',
    run_over: 'Dieses Spiel ist schon vorbei.',
    no_open_question: 'Es gibt keine offene Frage.',
    invalid_answer: 'Bitte gib eine Antwort.',
    question_unavailable: 'Gerade konnte keine Frage erstellt werden. Bitte nochmal versuchen.',
    no_life_left: 'Du hast kein 1UP zum Überspringen.',
    judge_unavailable:
      'Die Bewertung ist gerade nicht erreichbar. Dein Spiel ist pausiert; sende deine Antwort nochmal.',
    run_not_over: 'Nur beendete Spiele kommen in die Bestenliste.',
    run_already_claimed: 'Dieses Spiel steht schon in der Bestenliste.',
    invalid_handle: 'Der Name braucht 3 bis 8 Buchstaben (A-Z) oder Ziffern.',
  },
};

export const STRINGS: Record<Language, Strings> = { en, de };
