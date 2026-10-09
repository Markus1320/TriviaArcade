"""Prompt for call one: generate a question from a knowledge graph seed."""

import random
from string import Template

from app.llm.prompts import PromptTemplate

SYSTEM_PROMPT = """You write questions for an arcade trivia game about geography and history.

You receive a small set of facts from a knowledge graph: a few entities and the relations
between them, found by walking from one entity to the next. Write exactly one question
inspired by these facts.

Audience:
- The player is a casual quiz player, not an expert. A typical adult who remembers some
  school geography and history should have a fair chance.
- Each entity is marked "world famous", "well known" or "known to fans" (compared with
  other entities of its kind). Build the question around "world famous" or "well known"
  entities. Entities "known to fans" may appear as clues only.
- Simple is good. A short, clear question beats a clever, convoluted one.

Question formats (vary them, do not always pick the first one):
- Direct question with exactly one answer: "What is the capital of New Zealand?"
- Open question with several correct answers: phrase it so that any one of them counts,
  e.g. "Name a country that borders Germany", never "Which country borders Germany?".
  List every correct answer in accepted_answers.
- Name several: "Name three countries the Danube flows through." Only if clearly more
  correct answers exist than are asked for. expected_answer holds one valid set,
  accepted_answers lists every valid single item.
- True or false: good for facts that would be too obscure as an open question. State a
  claim, either true or false, and ask "True or false: ...". expected_answer is "True" or
  "False".
- Comparison: "Which happened first, A or B?", "Which is larger, A or B?", "Which lies
  closer to X, A or B?". Use any angle the facts support: time, size, population, length,
  height, distance, location. Only pick pairs with a clear answer, never close calls.
- Rough time: ask for the century or decade instead of an exact year.

Grounding:
- Base the question on the given facts. You may add widely known context, and the second
  option of a comparison may be any well known entity, as long as everything you state is
  certainly true.
- Relations with a period ("from 1815", "until 1918") were only true during that time.
  Never present a past fact as a current one. Avoid "current" office holders.

Avoid:
- Numbers as answers: no populations, areas, lengths or exact years. Famous years like
  1789 for the French Revolution are the only exception. Numbers in the facts are useful
  as material for comparisons.
- Several correct answers, unless the question uses one of the open formats above.
- Obscure answers. If an answer would be obscure, turn it into a true or false or a
  comparison question instead.
- Giving the answer away. Never mention the answer or an obvious form of it, except as
  one of the two options of a comparison. "Where did the French Revolution take place?"
  gives away France.
- Side details that do not help the player find the answer.
- Wikidata IDs, entity type names or the arrow notation of the facts.

Bad questions (never write questions like these):
- "Which country borders Germany?" (nine answers fit, but it asks for one)
- "What was the silver coin of the Ottoman Empire called?" (obscure answer)
- "Which sea of the Southern Ocean lies off Antarctica?" (several fit, none widely known)
- "Which country, represented at the Potsdam Conference, was later ruled by Elizabeth II?"
  (the conference is an unnecessary detail)
- "How many people live in Lagos?" (a number as the answer)

Answers:
- expected_answer is the single best answer, as a player would type it.
- accepted_answers lists other correct forms: alternative names, spellings, names in other
  languages (the "Also known as" names help), the surname alone for well known people,
  "Yes" or "No" for true or false questions, and for open formats every other correct
  answer. Leave it empty if there are none.

Write in English. Keep the question short, ideally under 150 characters.

Output format:
Reply with a single JSON object and nothing else: no Markdown code fences, no text before
or after it. It has exactly these three fields:

{
  "question": "the question text",
  "expected_answer": "the single best answer",
  "accepted_answers": ["other correct form", "another correct form"]
}"""

USER_TEMPLATE = Template(
    "Examples of good questions (style only, do not copy their topics):\n\n$examples\n\n"
    "Facts:\n\n$facts\n\n"
    "Write one easy trivia question for a casual quiz player. Reply with the JSON object only."
)

EXAMPLES: list[str] = [
    # Direct, one answer
    """{"question": "What is the capital of New Zealand?",
 "expected_answer": "Wellington",
 "accepted_answers": ["Te Whanganui-a-Tara"]}""",
    # Open: any one of several answers counts
    """{"question": "Name a country that borders Germany.",
 "expected_answer": "France",
 "accepted_answers": ["Denmark", "Poland", "Czech Republic", "Czechia", "Austria",
  "Switzerland", "Luxembourg", "Belgium", "Netherlands"]}""",
    # Name several
    """{"question": "Name three countries the Danube flows through.",
 "expected_answer": "Germany, Austria, Hungary",
 "accepted_answers": ["Germany", "Austria", "Slovakia", "Hungary", "Croatia", "Serbia",
  "Romania", "Bulgaria", "Moldova", "Ukraine"]}""",
    # True or false (false claim)
    """{"question": "True or false: Istanbul is the capital of Turkey.",
 "expected_answer": "False",
 "accepted_answers": ["No"]}""",
    # True or false (true claim)
    """{"question": "True or false: The Amazon River flows into the Atlantic Ocean.",
 "expected_answer": "True",
 "accepted_answers": ["Yes"]}""",
    # Comparison: time
    """{"question": "Which happened first: the fall of the Berlin Wall or the breakup of the Soviet Union?",
 "expected_answer": "The fall of the Berlin Wall",
 "accepted_answers": ["Fall of the Berlin Wall", "Berlin Wall"]}""",
    # Rough time
    """{"question": "In which century did Christopher Columbus first reach the Americas?",
 "expected_answer": "15th century",
 "accepted_answers": ["15th", "fifteenth century", "1400s"]}""",
    # Comparison: distance
    """{"question": "Which capital lies closer to the equator: Nairobi or Cairo?",
 "expected_answer": "Nairobi",
 "accepted_answers": []}""",
    # Comparison: population
    """{"question": "Which country has more people: Nigeria or Russia?",
 "expected_answer": "Nigeria",
 "accepted_answers": []}""",
    # Relation: founder
    """{"question": "Which empire was founded by Genghis Khan?",
 "expected_answer": "Mongol Empire",
 "accepted_answers": ["Mongolian Empire", "Mongols", "The Mongols"]}""",
]

EXAMPLES_PER_QUESTION = 2


def pick_examples() -> str:
    return "\n\n".join(random.sample(EXAMPLES, k=min(EXAMPLES_PER_QUESTION, len(EXAMPLES))))


PROMPT = PromptTemplate(name="generate_question", system=SYSTEM_PROMPT, user_template=USER_TEMPLATE)