"""Prompt templates stored as files in backend/prompts/.

A prompt file holds the system prompt, a line "=== USER ===", and the user message.
Placeholders use string.Template syntax ($name). Values are inserted verbatim and never
parsed again, so player input cannot inject further placeholders.
"""

from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
USER_MARKER = "=== USER ==="


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    system: str
    user_template: Template

    def render_user(self, **values: str) -> str:
        return self.user_template.substitute(values)


def load_prompt(name: str, directory: Path = PROMPTS_DIR) -> PromptTemplate:
    text = (directory / f"{name}.md").read_text(encoding="utf-8")
    if text.count(USER_MARKER) != 1:
        raise ValueError(f"prompt {name!r} must contain exactly one {USER_MARKER!r} line")
    system, user = text.split(USER_MARKER)
    return PromptTemplate(name=name, system=system.strip(), user_template=Template(user.strip()))
