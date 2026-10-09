"""Prompt template shape, used by app/llm/generator_prompt.py and app/llm/judge_prompt.py."""

from dataclasses import dataclass
from string import Template


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    system: str
    user_template: Template

    def render_user(self, **values: str) -> str:
        return self.user_template.substitute(values)
