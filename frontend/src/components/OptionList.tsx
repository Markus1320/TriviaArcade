import { type RefObject } from 'react';

import { strings } from '../strings';

// What is shown once a choice question has been judged: all options, with the correct ones
// and the ones the player picked (both as positions in options).
export interface ChoiceReveal {
  options: string[];
  correct: number[];
  selected: number[];
}

interface Props {
  options: string[];
  selected: number[];
  // Several options can be picked; without it picking one replaces the other.
  multiple?: boolean;
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

const MARK_TEXT: Record<Exclude<Mark, null>, string> = {
  right: strings.optionRight,
  missed: strings.optionMissed,
  wrong: strings.optionWrong,
};

export function OptionList({
  options,
  selected,
  multiple = false,
  disabled = false,
  onToggle,
  reveal,
  buttons,
}: Props) {
  if (reveal) {
    return (
      <ul className="options">
        {options.map((option, index) => {
          const mark = markOf(index, reveal);
          return (
            <li key={option} className={`option option--revealed option--${mark ?? 'other'}`}>
              <span className="option__text">{option}</span>
              {mark && <span className="option__mark">{MARK_TEXT[mark]}</span>}
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <ul className="options" role={multiple ? 'group' : 'radiogroup'}>
      {options.map((option, index) => {
        const picked = selected.includes(index);
        return (
          <li key={option}>
            <button
              type="button"
              ref={(element) => {
                if (buttons) buttons.current[index] = element;
              }}
              role={multiple ? 'checkbox' : 'radio'}
              aria-checked={picked}
              className={picked ? 'option option--picked' : 'option'}
              disabled={disabled}
              onClick={() => onToggle?.(index)}
            >
              <span className="option__key" aria-hidden="true">
                {index + 1}
              </span>
              <span className="option__text">{option}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
