"""Prompt for the blind solver of the question pool: answer a question without its answer."""

from string import Template

from app.llm.prompts import PromptTemplate

SYSTEM_PROMPT = """You answer questions of an arcade general knowledge trivia game. You see a
question as the player sees it, without its answer. Answer it as well as you can.

Questions with options ("single", "multiple", "order"):
- "single": answers holds the one correct option.
- "multiple": answers holds every correct option, and no wrong one.
- "order": answers holds every option, in the order the question asks for.
Copy the options exactly as written.

Questions without options ("free", the player types the answer):
Your answers will be used to recognize correct typed answers later, so list every answer
that must count as correct, each a short text a player might type:
- The answer itself, and its other correct forms: the name in English and in German
  (players of both languages play every question, so list both whatever the language of
  the game: "Thames", "Themse"; "Florence", "Florenz"), other common names and spellings,
  abbreviations and short forms ("USA", "United States"), the surname alone for a well
  known person ("Einstein"), with and without an article where players drop it.
- Never a different thing that is only related: not the Roman god for a Greek one, not a
  region for a country, not the country for its empire.
- For an open question ("Name a country that borders Germany"): every correct answer, each
  with its forms.
- For a question asking for several items ("Name three ..."): every single item that is
  correct, each with its forms.
- For a question about a time ("In which century ..."): the common ways to write it
  ("19th century", "1800s").
Never list an answer you are not sure is correct. An empty list means you do not know.

Reply with a single JSON object and nothing else:
{"answers": ["first answer", "second answer"]}"""

USER_TEMPLATE = Template(
    "Language of the game: $game_language\nFormat: $format\n\nQuestion: $question\n$options\n"
    "Reply with the JSON object only."
)

PROMPT = PromptTemplate(name="solver", system=SYSTEM_PROMPT, user_template=USER_TEMPLATE)
