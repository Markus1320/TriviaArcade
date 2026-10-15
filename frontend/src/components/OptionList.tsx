import { type RefObject } from 'react';

import { useStrings } from '../language/languageState';

// What is shown once a choice question has been judged: all options, with the correct ones
// and the ones the player picked (both as positions in options). For order questions both
// lists are in order: the correct order and the order the player tapped.
export interface ChoiceReveal {
  options: string[];
  correct: number[];
  selected: number[];
  ordered: boolean;
}

interface Props {
  options: string[];
  selected: number[];
  // Several options can be picked; without it picking one replaces the other.
  multiple?: boolean;
  // Every option is tapped in order; selected holds the tapped order.
  ordered?: boolean;
  disabled?: boolean;
  onToggle?: (index: number) => void;
  // Set after the verdict: marks right, missed and wrongly picked options. Read only then.
  reveal?: ChoiceReveal;
  // Filled with the option buttons, so the screen can move the keyboard focus.
  buttons?: RefObject<(HTMLButtonElement | null)[]>;
}

type Mark = 'right' | 'missed' | 'wrong' | null;

function markOf(index: number, reveal: ChoiceReveal): Mark {
  const picked = reveal.selected.includes(index);
  if (reveal.correct.includes(index)) return picked ? 'right' : 'missed';
  return picked ? 'wrong' : null;
}

export function OptionList({
  options,
  selected,
  multiple = false,
  ordered = false,
  disabled = false,
  onToggle,
  reveal,
  buttons,
}: Props) {
  const strings = useStrings();
  const markText: Record<Exclude<Mark, null>, string> = {
    right: strings.optionRight,
    missed: strings.optionMissed,
    wrong: strings.optionWrong,
  };
  if (reveal?.ordered) {
    return <OrderReveal reveal={reveal} />;
  }
  if (reveal) {
    return (
      <ul className="options">
        {options.map((option, index) => {
          const mark = markOf(index, reveal);
          return (
            <li key={option} className={`option option--revealed option--${mark ?? 'other'}`}>
              <span className="option__text">{option}</span>
              {mark && <span className="option__mark">{markText[mark]}</span>}
            </li>
          );
        })}
      </ul>
    );
  }
  const role = ordered || multiple ? 'group' : 'radiogroup';
  return (
    <ul className="options" role={role}>
      {options.map((option, index) => {
        const picked = selected.includes(index);
        const position = selected.indexOf(index) + 1;
        return (
          <li key={option}>
            <button
              type="button"
              ref={(element) => {
                if (buttons) buttons.current[index] = element;
              }}
              role={ordered ? undefined : multiple ? 'checkbox' : 'radio'}
              aria-checked={ordered ? undefined : picked}
              aria-pressed={ordered ? picked : undefined}
              aria-label={ordered && picked ? `${String(position)}: ${option}` : undefined}
              className={picked ? 'option option--picked' : 'option'}
              disabled={disabled}
              onClick={() => onToggle?.(index)}
            >
              {/* The digit key; hidden for order questions, where it would be confused with
                  the place (the digit keys still work). */}
              {!ordered && (
                <span className="option__key" aria-hidden="true">
                  {index + 1}
                </span>
              )}
              <span className="option__text">{option}</span>
              {ordered && picked && (
                <span className="option__position" aria-hidden="true">
                  {position}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// The items in the correct order, each marked whether the player put it in this place; a
// wrong one shows where the player put it, or that it was not tapped at all.
function OrderReveal({ reveal }: { reveal: ChoiceReveal }) {
  const strings = useStrings();
  return (
    <ol className="options">
      {reveal.correct.map((index, place) => {
        const tapped = reveal.selected.indexOf(index);
        const right = tapped === place;
        const mark = right
          ? strings.optionRight
          : tapped === -1
            ? strings.optionMissed
            : strings.yourPlace(tapped + 1);
        return (
          <li
            key={reveal.options[index]}
            className={`option option--revealed option--${right ? 'right' : 'wrong'}`}
          >
            <span className="option__key">{place + 1}</span>
            <span className="option__text">{reveal.options[index]}</span>
            <span className="option__mark">{mark}</span>
          </li>
        );
      })}
    </ol>
  );
}
