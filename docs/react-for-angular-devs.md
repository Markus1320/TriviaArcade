# React for Angular developers

What you know from Angular, and where it is in this project's React code. React is
smaller than Angular: it only draws components. Everything else (talking to the server,
switching screens) is plain TypeScript.

| Angular | React | In this project |
|---|---|---|
| Component class + template | A function that returns JSX | every file in `screens/` and `components/` |
| `@Input()` | the function's parameter (`props`) | `Hud({ number, streak, ... })` in `Hud.tsx` |
| `@Output()` + `EventEmitter` | a function passed as a prop | `onNext` in `Verdict.tsx`, `onGameOver` in `QuestionScreen.tsx` |
| Class fields + change detection | `useState`: a value and a function to change it | `const [answer, setAnswer] = useState('')` in `AnswerForm.tsx` |
| `ngOnInit` / `ngOnDestroy` | `useEffect(() => { ...; return cleanup; }, [deps])` | loading the question in `QuestionScreen.tsx`, the key listener in `AnswerForm.tsx` |
| `@ViewChild` | `useRef` | `optionButtons` in `AnswerForm.tsx` |
| Service with `providedIn: 'root'` | a plain module you import | `api` in `api/client.ts` |
| Service holding shared state (DI) | Context: a Provider at the top, a hook to read it | `LanguageProvider.tsx` + `useStrings()`, `SoundProvider.tsx` + `useSound()` |
| Router | a state variable saying which screen is shown | `screen` in `App.tsx` |
| `HttpClient` + Observable | `fetch` + Promise (`.then`, `.catch`) | `request()` in `api/client.ts` |
| Pipe | a plain function called in JSX | `strings.questionNumber(number)` |

## Templates become JSX

JSX is HTML-like syntax inside TypeScript. Curly braces hold any expression.

| Angular template | JSX |
|---|---|
| `{{ question.text }}` | `{question.text}` |
| `*ngIf="error"` | `{error && <p>...</p>}` or `{error ? <A /> : <B />}` |
| `*ngFor="let o of options"` | `{options.map((o, i) => <li key={i}>{o}</li>)}` |
| `[class.active]="on"` | `className={on ? 'button active' : 'button'}` (`class` is a keyword) |
| `(click)="next()"` | `onClick={next}` |
| `[(ngModel)]="answer"` | `value={answer} onChange={(e) => setAnswer(e.target.value)}` |
| `<app-hud [score]="s">` | `<Hud streak={s} />` |

## The three things that are different

1. **The function runs again on every change.** When state changes, React calls the
   component function again and compares the new JSX with the old one. There is no
   change detection to think about, but anything computed in the function body is
   recomputed each time. That is fine for small things like `const isChoice = ...` in
   `AnswerForm.tsx`.
2. **State is replaced, not changed.** `setSelected([...current, index])` makes a new
   array; `selected.push(index)` would change the array without React noticing.
3. **`key` gives a component an identity.** In `QuestionScreen.tsx`,
   `<AnswerForm key={question.question_id} ...>` makes React throw away the old form and
   start an empty one for every new question.

## Hooks rules

Functions starting with `use` (`useState`, `useEffect`, `useStrings`) are hooks. Call them
at the top of the component, never inside an `if` or a loop: React tells them apart by
their order. ESLint (`react-hooks`) reports a break of this rule.

In development, `<StrictMode>` in `main.tsx` runs every effect twice on purpose, to show
effects that do not clean up after themselves. The built game does not.

## Where to start reading

`main.tsx` → `App.tsx` (which screen) → `screens/QuestionScreen.tsx` (one question) →
`components/AnswerForm.tsx`. [how-it-works.md](how-it-works.md) follows the same path
with the server side.
