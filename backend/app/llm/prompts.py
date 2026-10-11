"""Prompt template shape, used by app/llm/generator_prompt.py and app/llm/judge_prompt.py."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from string import Template

DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class PromptTemplate:
    """A system prompt and a user template.

    The system prompt is always English. The user message can exist in several languages
    (localized_user_templates, by language code); user_template is the English one and the
    fallback.
    """

    name: str
    system: str
    user_template: Template
    localized_user_templates: Mapping[str, Template] = field(default_factory=dict)

    def render_user(self, language: str = DEFAULT_LANGUAGE, **values: str) -> str:
        template = self.localized_user_templates.get(language, self.user_template)
        return template.substitute(values)
