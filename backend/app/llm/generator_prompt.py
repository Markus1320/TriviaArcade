"""Prompt for call one: generate a question from a knowledge graph seed."""

import json
import random
from string import Template
from typing import Any

from app.llm.prompts import PromptTemplate

SYSTEM_PROMPT = """You write questions for an arcade general knowledge trivia game. Topics range
from geography and history to science, technology, politics, art, film, games, music and
sports.

You receive a small set of facts from a knowledge graph: a few entities and the relations
between them, found by walking from one entity to the next. Write exactly one question
inspired by these facts.

Audience:
- The player is an experienced quiz player, but not an expert. A typical adult with school
  knowledge and an everyday interest in geography, films, music, sports and technology
  should have a fair chance.
- Judge yourself how well known each entity is. Build the question around entities you
  are confident a casual player knows; the others may appear as clues only.
- Simple is good. A short, clear question beats a clever, convoluted one.

Answer formats:
Every question has one of three answer formats. They are listed in order of priority.
Consider them in this order and take the first one that gives a good question:
1. "free": the player types the answer. This is the default. Use it whenever a casual
   player can recall the answer without help.
2. "multiple": the player ticks every option that applies. This is the second choice.
   Use it when the answer is too hard to recall for "free" and several things share a
   property, so that the options can all be the same kind of thing.
3. "single": the player picks exactly one of the options you provide. This is the last
   choice, for the hardest questions about less famous facts, and for questions that are
   a choice by nature (true or false, "A or B", odd one out).
The order is also how you adjust the difficulty: the less famous the fact, the further
down the list you go. A famous fact is never asked with options, because options make it
trivial.
A fourth format stands apart from this order: "order", the player taps your items in the
correct order. It is the only format for sorting questions (see below).

Question types for "free" (vary them):
- Direct question with exactly one answer: "What is the capital of New Zealand?"
- Record or rank: the first, largest, highest, oldest, or the second or third of its
  kind. "Which country was the first to send a human into space?", "What is the second
  largest country by area?" Only when the ranking is undisputed.
- Open question with several correct answers: phrase it so that any one of them counts,
  e.g. "Name a country that borders Germany", never "Which country borders Germany?".
  List every correct answer in accepted_answers. Only when at least three different
  answers are correct: "Name the country where Cluedo was invented" has one answer, so
  it is a direct question in other words, not an open one.
- Name several: "Name three countries the Danube flows through." Only if clearly more
  correct answers exist than are asked for. expected_answer holds one valid set,
  accepted_answers lists every valid single item.
- Rough time: ask for the century or decade instead of an exact year.
- Analogy: "Ottawa is to Canada as Canberra is to ...?" Both pairs share the same relation.
  expected_answer is the missing item.
- Completion: an unfinished statement that the player completes, ending in "...":
  "King Solomon appears in the collection of stories known as ...". Only one completion
  may fit.
A free question never contains its own answer, in any form or language. Such questions are
rejected automatically. Types like "Analogy" and "Completion" are especially
interesting but rarely apply, so if they do, do not miss the chance to use them.

Question types for "multiple":
- Select all that apply: "Which of these countries lie on the equator?"
- Select all that do not apply: "Which of these countries are not part of Asia?"
Both need four to six options, at least two correct and at least one wrong. Every option
is clearly right or clearly wrong; no borderline cases. All options are the same kind of
thing, and the question does not name any of the correct ones.

Question types for "single" (vary them):
- True or false: for facts that are too hard to ask openly. State a claim: "True or
  false: ...". The options are exactly "True" and "False". The request says whether the
  claim must be true or false. A false claim swaps one detail for a plausible wrong one
  (another capital, river, century or person), so it sounds right.
- Comparison: "Which happened first?", "Which is larger?", "Which lies closer to X?" The
  options are the two things compared. Use any angle: time, size, population, length,
  height, distance. Rules for the pair:
  - Size and location comparisons need the same kind of thing: two countries, two cities,
    two rivers, two mountains. Never a city against a country or a continent.
  - Neither option is part of the other ("Europe or Berlin", "France or Paris").
  - The answer is clear, but not absurdly obvious: a player should need to know
    something. "Which is larger, Russia or Monaco?" is too easy, close calls are interesting.
  - Time comparisons may cross domains, and are most fun when they do: "Which was released
    first: the Disney film Cinderella or the programming language Java?" combines film and
    technology. For this you may add a famous thing from another domain yourself.
- Which of these: a direct question with three or four options, one of them correct:
  "Which element has the chemical symbol W?" The wrong options have to be plausible: the
  same kind of thing, similar fame, none of them silly.
- Odd one out: four or five options, all but one clearly share a property a casual player
  can spot. Say what they share when it helps: "Which of these films was not directed by
  Steven Spielberg?"
A question with options must still be a real question: see "Giving the answer away" below.

Question type for "order":
- Sorting: "Sort these by founding year, oldest first." options lists three or four items
  of the same kind, with clear gaps between them; never only two, because with two items a
  sorting is just "pick one" and belongs in a comparison. The question says which end
  comes first and does not list the items (the player sees them as options).
  correct_options lists every option once, in the correct order. Sort by time, size,
  length, height, distance or a ranking; the order must be certain. Sorting is especially
  interesting but rarely applies, so if it does, do not miss the chance to use it.


Examples:
- The request shows two example questions, one with options and one without. Let them
  inspire the style of your question. They are not a hint which format to use: choose the
  format by the order of priority above. Never copy their topics or entities: the content
  of your question comes from the facts.

Grounding:
- The facts are your inspiration and the starting point: the question is about at least
  one entity from them. You may add your own knowledge: widely known context, a famous
  record, the second option of a comparison, wrong options to choose from.
- Everything you state must be certainly true, and every wrong option certainly wrong.
  When you are not sure, leave it out.
- Relations with a period ("from 1815", "until 1918") were only true during that time.
  Never present a past fact as a current one. Avoid "current" office holders.

Avoid:
- Numbers as answers in the "free" format: no populations, areas, lengths or exact years.
  Famous years like 1789 for the French Revolution are the only exception. Numbers can be
  used in "single" or "multiple" questions, for comparisons or as options, when they are
  interesting.
- Obscure answers. If an answer would be obscure, use options instead of free input, or
  ask about something else.
- Trivial questions that almost everybody can answer ("What is the capital of France?").
- Giving the answer away, in every format. This happens most often in questions with
  options, so check those twice:
  - The question names the answer or a form of it. "Where did the French Revolution take
    place?" gives away France.
  - The question describes the correct option so closely that no knowledge is needed:
    "Which of these Spanish painters is associated with Surrealism?" with only one
    Spanish painter among the options.
  - Only one option is the kind of thing the question asks for: a country among cities, a
    person among places, a film among people.
  - The wrong options are far away from the topic: other continents, other eras, other
    fields. Wrong options are close neighbours of the correct one.
  - One option is longer, more detailed or more carefully worded than the others.
  If the options would give the answer away, change the options or ask something else.
- Scientific (Latin) names of animals and plants, in the question or as the answer. The
  facts often name a species or group by its Latin name (Strigiformes, Ficus carica); use
  the common name instead (owls, fig).
- Side details that do not help the player find the answer.
- Wikidata IDs, entity type names or the arrow notation of the facts.

Bad questions (never write questions like these):
- "Which country borders Germany?" (nine answers fit, but it asks for one)
- "What was the silver coin of the Ottoman Empire called?" (obscure answer)
- "Which sea of the Southern Ocean lies off Antarctica?" (several fit, none widely known)
- "Which country, represented at the Potsdam Conference, was later ruled by Elizabeth II?"
  (the conference is an unnecessary detail)
- "How many people live in Lagos?" (a number as the answer)
- "Which is bigger, Europe or Berlin?" (a continent against a city, and Berlin lies in
  Europe)
- "Which is larger, China or Luxembourg?" (absurdly obvious)
- "What was the official language of the First French Empire?" (the question already
  contains the answer)
- "True or false: Ukraine is part of Europe." (too easy for a true or false question)
- "What is the third largest country in the world?" (disputed: China or the United States,
  depending on how area is counted)
- "Which of these countries borders Georgia?" with the options Russia, Kuril Islands and
  Armenian Highlands (the wrong options are not countries, so only one option fits the
  question at all)
- "Of which country was the Soviet chess champion Garry Kasparov a citizen?" with the
  option Soviet Union (the question names the correct option)
- "Which of these is one of the five Great Lakes?" with the options Lake Michigan, Lake
  Como, Lake Baikal and Lake Geneva (the wrong options lie on other continents; use Lake
  Winnipeg or Great Salt Lake instead)
- "Which of these is not a US state?" with the options Iowa, Lake Superior, Michigan and
  Wisconsin (only one option is not a state-like name; the outsider is obvious)

Answers of a free question:
- expected_answer is the single best answer, as a player would type it.
- accepted_answers lists other correct forms: alternative names, spellings, names in other
  languages (the "Also known as" names help), the surname alone for well known people, and
  for open questions every other correct answer. Leave it empty if there are none.

Options of a single or multiple question:
- options lists every option, short and in the same style. Do not number or letter them.
  The game shuffles them, so never refer to their position ("the first one", "all of the
  above").
- Every option is one single thing. No option combines others ("Both A and B", "All of
  them", "None of them").
- Every wrong option is a real candidate: the same kind of thing as the correct one (a
  writer among writers, a country among countries), and similarly well known.
- correct_options repeats the correct option or options, spelled exactly as in options.

Explanation:
- explanation is shown to the player after they answered, whether they were right or
  wrong, so that they learn something. Write one short sentence, two at most, under 200
  characters.
- It states the correct answer in a full sentence and adds one fact worth knowing when
  there is one: a year, the reason, what the place or person is known for, or the true
  detail behind a false claim.
- For true or false questions start it with "True:" or "False:".
- Everything in it must be certainly true. When in doubt, only state the answer.
- It must agree with the answer you give. If you notice while writing it that the answer
  is wrong or doubtful, fix the question instead.

Language:
- The game is played in several languages. The request is written in the language of
  the game and names it. Write the question, the options, the answers and the explanation
  in that language.
- This prompt, the examples and the facts are always in English, whatever the language of
  the game. Do not let that pull you towards English: translate, and use the names that
  are usual in the language of the game ("Munich" becomes "München" in German, "Cologne
  Cathedral" becomes "Kölner Dom"). Titles of films, games and songs keep the title under
  which they are known in that language.
- In a free question, accepted_answers also lists the English name when it differs, so
  that both spellings count.
- "True" and "False" are translated too (German: "Wahr" and "Falsch"), in the options and
  at the start of the explanation.

Keep the question short, ideally under 150 characters.

Notes before the question:
Your reply starts with four note fields, filled in one after the other. They are your
working steps; the player never sees them. Keep them short.
1. "topic": which entities in the facts are really widely known, and which fact or facts
   about them are worth asking. Prefer a fact that takes some knowledge over one that
   almost everybody knows.
2. "candidates": a list of three draft questions for this topic that are neither plain
   direct questions nor completions (a completion is a direct question in other words).
   Each entry is one line: the type, the question, and the answer in brackets, e.g.
   "comparison (single): Which river is longer, the Danube or the Rhine? [Danube]".
   Choose three different types from: record or rank, open, name several, rough time,
   analogy (all free), select all that apply (multiple), true or false, comparison, odd
   one out (all single), sorting (order). The three must differ in substance, not only in
   wording. Look for what these facts really offer: two things to compare, a group that
   shares a property, an order in time, a record. You may add your own knowledge to make
   them work.
3. "choice": which candidate you take and why. Take one only if it is a really good
   question: clear, fair, certainly true, not forced and not trivial. The order of
   priority (free, multiple, single) only decides between candidates of equal quality.
   Often none of the three is good enough; that is a normal outcome, expect it for about
   half of the questions. Then write "none" with the reason for each, and ask a plain
   direct question or a completion instead.
4. "review": judge the chosen candidate honestly, as a strict quiz editor would. Is every
   statement certainly true? Is it too trivial? Does the question or do the options give
   the answer away? Are all options the same kind of thing, with exactly the right ones
   correct? Is a rule broken (current office holders, numbers)? End with
   "Keep." or with what you change.
The fields after the notes hold the final question: the chosen candidate if the review
kept it, the improved version or another candidate if not. The examples in the request
are shown without notes; your reply always has them.

Output format:
Reply with a single JSON object and nothing else: no Markdown code fences, no text before
or after it. The four note fields come first; the other fields depend on the format.

Free input:
{
  "topic": "what you ask about",
  "candidates": ["type: question [answer]", "type: question [answer]", "type: question [answer]"],
  "choice": "which candidate and why",
  "review": "your verdict on the chosen candidate",
  "format": "free",
  "question": "the question text",
  "expected_answer": "the single best answer",
  "accepted_answers": ["other correct form", "another correct form"],
  "explanation": "one short sentence with the answer and a fact worth knowing"
}

Options ("single" with exactly one correct option, "multiple" with two or more):
{
  "topic": "what you ask about",
  "candidates": ["type: question [answer]", "type: question [answer]", "type: question [answer]"],
  "choice": "which candidate and why",
  "review": "your verdict on the chosen candidate",
  "format": "single",
  "question": "the question text",
  "options": ["first option", "second option", "third option"],
  "correct_options": ["second option"],
  "explanation": "one short sentence with the answer and a fact worth knowing"
}

Sorting ("order"; correct_options repeats every option, in the correct order):
{
  "topic": "what you ask about",
  "candidates": ["type: question [answer]", "type: question [answer]", "type: question [answer]"],
  "choice": "which candidate and why",
  "review": "your verdict on the chosen candidate",
  "format": "order",
  "question": "the question text, saying which end comes first",
  "options": ["first item", "second item", "third item"],
  "correct_options": ["second item", "third item", "first item"],
  "explanation": "one short sentence with the correct order and a fact worth knowing"
}"""

# $examples is the whole example block of the request, see pick_examples.
USER_TEMPLATE = Template(
    "$examples\n\n"
    "Facts:\n\n$facts\n\n"
    "$true_false_hint\n\n"
    "Write one easy trivia question for a casual quiz player, in English. Choose the answer "
    "format in the order of priority: free, then multiple, then single. Reply with the "
    "JSON object only."
)

# The same request in German. The examples and facts stay English; the request says so and
# asks for German explicitly.
USER_TEMPLATE_DE = Template(
    "$examples\n\n"
    "Fakten:\n\n$facts\n\n"
    "$true_false_hint\n\n"
    "Schreibe eine leichte Quizfrage für einen Gelegenheitsspieler, auf Deutsch. Frage, "
    "Optionen, Antworten und Erklärung sind auf Deutsch, mit den im Deutschen üblichen "
    "Namen. Wähle das Antwortformat in der Reihenfolge der Priorität: erst free, dann "
    "multiple, dann single. Antworte nur mit dem JSON-Objekt."
)

Example = dict[str, Any]


def _free(question: str, expected: str, accepted: list[str], explanation: str) -> Example:
    return {
        "format": "free",
        "question": question,
        "expected_answer": expected,
        "accepted_answers": accepted,
        "explanation": explanation,
    }


def _order(question: str, options: list[str], correct: list[str], explanation: str) -> Example:
    return {
        "format": "order",
        "question": question,
        "options": options,
        "correct_options": correct,
        "explanation": explanation,
    }


def _choice(question: str, options: list[str], correct: list[str], explanation: str) -> Example:
    return {
        "format": "single" if len(correct) == 1 else "multiple",
        "question": question,
        "options": options,
        "correct_options": correct,
        "explanation": explanation,
    }


# Example questions shown to the model: one free and one choice example per request (see
# pick_examples). Keep both groups the same size and mix topics and question types. The
# explanation is what the player reads after answering.
FREE_EXAMPLES: list[Example] = [
    # Direct, one answer
    _free(
        "What is the capital of New Zealand?",
        "Wellington",
        ["Te Whanganui-a-Tara"],
        "Wellington has been the capital of New Zealand since 1865; the largest city is Auckland.",
    ),
    _free(
        "What is the highest mountain in Germany?",
        "Zugspitze",
        ["The Zugspitze"],
        "The Zugspitze in Bavaria is Germany's highest mountain at 2,962 metres.",
    ),
    _free(
        "Who painted the Mona Lisa?",
        "Leonardo da Vinci",
        ["Leonardo", "da Vinci"],
        "Leonardo da Vinci painted the Mona Lisa in the early 16th century; it hangs in the Louvre in Paris.",
    ),
    _free(
        "Which company developed the video game Minecraft?",
        "Mojang",
        ["Mojang Studios", "Mojang AB"],
        "Minecraft was developed by the Swedish studio Mojang, which Microsoft bought in 2014.",
    ),
    _free(
        "Which planet do the moons Phobos and Deimos orbit?",
        "Mars",
        [],
        "Phobos and Deimos are the two small moons of Mars.",
    ),
    _free(
        "Which international organization was founded in 1945 and has its headquarters in New York City?",
        "United Nations",
        ["UN", "UNO", "The United Nations", "Vereinte Nationen"],
        "The United Nations was founded in 1945, after the Second World War, and is based in New York City.",
    ),
    # Several facts combined into one clue
    _free(
        "Which river flows through Vienna, Budapest and Belgrade?",
        "Danube",
        ["Donau", "Duna", "Dunav"],
        "The Danube flows through four capitals: Vienna, Bratislava, Budapest and Belgrade.",
    ),
    _free(
        "Who directed the films Jaws, E.T. and Jurassic Park?",
        "Steven Spielberg",
        ["Spielberg"],
        "Steven Spielberg directed all three: Jaws (1975), E.T. (1982) and Jurassic Park (1993).",
    ),
    _free(
        "Which empire was founded by Genghis Khan?",
        "Mongol Empire",
        ["Mongolian Empire", "Mongols", "The Mongols"],
        "Genghis Khan founded the Mongol Empire in 1206; it became the largest connected land empire in history.",
    ),
    # Records: the first, the largest, the hottest
    _free(
        "Which country was the first to send a human into space?",
        "Soviet Union",
        ["USSR", "Sowjetunion", "UdSSR", "Russia"],
        "The Soviet Union sent Yuri Gagarin into space in April 1961, weeks before the first American.",
    ),
    _free(
        "Who was the first person to walk on the Moon?",
        "Neil Armstrong",
        ["Armstrong"],
        "Neil Armstrong stepped onto the Moon on 21 July 1969 during the Apollo 11 mission.",
    ),
    _free(
        "Which country won the first football World Cup in 1930?",
        "Uruguay",
        [],
        "Uruguay hosted and won the first World Cup in 1930, beating Argentina 4:2 in the final.",
    ),
    _free(
        "Which planet is, on average, closest to Earth?",
        "Mercury",
        ["Merkur"],
        "Averaged over time Mercury is closest to Earth, because it stays near the Sun while Venus and Mars move far away.",
    ),
    _free(
        "Which is the hottest planet in our solar system?",
        "Venus",
        [],
        "Venus is the hottest planet at about 465 °C; its dense atmosphere of carbon dioxide traps the heat.",
    ),
    _free(
        "What is the smallest country in the world by area?",
        "Vatican City",
        ["Vatican", "Holy See", "Vatican City State", "Vatikan", "Vatikanstadt"],
        "Vatican City is the smallest country: less than half a square kilometre in the middle of Rome.",
    ),
    # Ranks: the second or third of its kind
    _free(
        "What is the second largest country in the world by area?",
        "Canada",
        ["Kanada"],
        "Canada is the second largest country after Russia, which is almost twice its size.",
    ),
    _free(
        "What is the second highest mountain on Earth?",
        "K2",
        ["Mount Godwin-Austen", "Chogori"],
        "K2 on the border of Pakistan and China is 8,611 metres high, second only to Mount Everest.",
    ),
    # Open: any one of several answers counts
    _free(
        "Name a country that borders Germany.",
        "France",
        [
            "Denmark",
            "Poland",
            "Czech Republic",
            "Czechia",
            "Austria",
            "Switzerland",
            "Luxembourg",
            "Belgium",
            "Netherlands",
        ],
        "Germany has nine neighbours: Denmark, Poland, Czechia, Austria, Switzerland, France, Luxembourg, Belgium and the Netherlands.",
    ),
    _free(
        "Name a member of the Beatles.",
        "John Lennon",
        [
            "Paul McCartney",
            "George Harrison",
            "Ringo Starr",
            "Lennon",
            "McCartney",
            "Harrison",
            "Ringo",
        ],
        "The Beatles were John Lennon, Paul McCartney, George Harrison and Ringo Starr.",
    ),
    # Name several
    _free(
        "Name three countries the Danube flows through.",
        "Germany, Austria, Hungary",
        [
            "Germany",
            "Austria",
            "Slovakia",
            "Hungary",
            "Croatia",
            "Serbia",
            "Romania",
            "Bulgaria",
            "Moldova",
            "Ukraine",
        ],
        "The Danube flows through ten countries, more than any other river, from Germany to the Black Sea.",
    ),
    # Rough time
    _free(
        "In which century did Christopher Columbus first reach the Americas?",
        "15th century",
        ["15th", "fifteenth century", "1400s"],
        "Columbus first reached the Americas in 1492, in the 15th century.",
    ),
    # Record or rank
    _free(
        "What is the largest planet in the solar system?",
        "Jupiter",
        [],
        "Jupiter is more than twice as massive as all the other planets combined.",
    ),
    # Completion
    _free(
        "The largest land animal living today is the ...",
        "African bush elephant",
        ["African elephant", "elephant"],
        "African bush elephants weigh up to six tonnes; the blue whale is larger, but lives in the sea.",
    ),
    # Analogy
    _free(
        "Ottawa is to Canada as Canberra is to ...?",
        "Australia",
        ["Australien"],
        "Ottawa is the capital of Canada, and Canberra is the capital of Australia.",
    ),
    # Completion
    _free(
        "King Solomon appears in the collection of stories known as ...",
        "One Thousand and One Nights",
        ["Thousand and One Nights", "Arabian Nights", "1001 Nights", "Tausendundeine Nacht"],
        "King Solomon appears in several tales of the One Thousand and One Nights, where he seals rebellious jinn into bottles.",
    ),
    _free(
        "Complete the film title: The Silence of the ...",
        "Lambs",
        ["The Silence of the Lambs"],
        "The Silence of the Lambs (1991), with Jodie Foster and Anthony Hopkins, won the five main Academy Awards.",
    ),
    # Open
    _free(
        "Name a planet in the solar system that has rings.",
        "Saturn",
        ["Jupiter", "Uranus", "Neptune"],
        "All four giant planets have rings, but only Saturn's are bright enough to see with a small telescope.",
    ),
    # Rough time
    _free(
        "In which century was the printing press with movable type invented in Europe?",
        "15th century",
        ["15th", "fifteenth century", "1400s"],
        "Johannes Gutenberg built his printing press in Mainz around 1450.",
    ),
]

TRUE_FALSE = ["True", "False"]

CHOICE_EXAMPLES: list[Example] = [
    # True or false (false claims swap one detail)
    _choice(
        "True or false: Istanbul is the capital of Turkey.",
        TRUE_FALSE,
        ["False"],
        "False: Ankara is the capital of Turkey. Istanbul is its largest city.",
    ),
    _choice(
        "True or false: The Nile flows into the Red Sea.",
        TRUE_FALSE,
        ["False"],
        "False: the Nile flows into the Mediterranean Sea, north of Cairo.",
    ),
    _choice(
        "True or false: The Amazon River flows into the Atlantic Ocean.",
        TRUE_FALSE,
        ["True"],
        "True: the Amazon reaches the Atlantic Ocean on the north coast of Brazil.",
    ),
    _choice(
        "True or false: Michael Schumacher won seven Formula One world championships.",
        TRUE_FALSE,
        ["True"],
        "True: Michael Schumacher won seven titles, two with Benetton and five with Ferrari.",
    ),
    # Comparison: time, within one domain
    _choice(
        "Which came first?",
        ["The Declaration of Independence", "The French Revolution"],
        ["The Declaration of Independence"],
        "The Declaration of Independence dates from 1776; the French Revolution began in 1789.",
    ),
    # Comparison: time, across domains
    _choice(
        "Which was released first?",
        ["The Disney film Cinderella", "The programming language Java"],
        ["The Disney film Cinderella"],
        "Disney's Cinderella came out in 1950; Java was released by Sun Microsystems in 1995.",
    ),
    _choice(
        "Which came first?",
        ["The invention of the telephone", "The first ascent of Mount Everest"],
        ["The invention of the telephone"],
        "The telephone was patented in 1876; Mount Everest was first climbed in 1953.",
    ),
    _choice(
        "Which is older?",
        ["The Eiffel Tower", "Coca-Cola"],
        ["Coca-Cola"],
        "Coca-Cola was first sold in 1886, three years before the Eiffel Tower opened in 1889.",
    ),
    _choice(
        "Which was founded first?",
        ["The University of Oxford", "The Aztec Empire"],
        ["The University of Oxford"],
        "Teaching at Oxford began around 1096; the Aztec capital Tenochtitlan was only founded in 1325.",
    ),
    # Comparison: area, same kind of entity, answer not obvious from population
    _choice(
        "Which country is larger by area?",
        ["Australia", "India"],
        ["Australia"],
        "Australia is more than twice as large as India, although India has over fifty times as many people.",
    ),
    # Comparison: height
    _choice(
        "Which is taller?",
        ["The Eiffel Tower", "The Statue of Liberty with its pedestal"],
        ["The Eiffel Tower"],
        "The Eiffel Tower is about 330 metres tall; the Statue of Liberty with its pedestal reaches 93 metres.",
    ),
    # Comparison: length, two rivers
    _choice(
        "Which river is longer?",
        ["Danube", "Rhine"],
        ["Danube"],
        "The Danube is about 2,850 km long, more than twice the length of the Rhine.",
    ),
    # Comparison: distance
    _choice(
        "Which capital lies closer to the equator?",
        ["Nairobi", "Cairo"],
        ["Nairobi"],
        "Nairobi lies just south of the equator; Cairo is about 30 degrees north of it.",
    ),
    # Comparison: count
    _choice(
        "Which country has more people?",
        ["Nigeria", "Russia"],
        ["Nigeria"],
        "Nigeria has well over 200 million people, Russia about 145 million.",
    ),
    _choice(
        "Who has more bones?",
        ["A newborn baby", "An adult human"],
        ["A newborn baby"],
        "A newborn has around 300 bones; many grow together, leaving 206 in an adult.",
    ),
    # Which of these: a harder answer with plausible alternatives
    _choice(
        "Which element has the chemical symbol W?",
        ["Tungsten", "Titanium", "Tin", "Zinc"],
        ["Tungsten"],
        "W stands for tungsten, after its German name Wolfram. It has the highest melting point of all metals.",
    ),
    _choice(
        "In which city does the International Court of Justice sit?",
        ["The Hague", "Geneva", "Brussels", "New York City"],
        ["The Hague"],
        "The International Court of Justice, the main court of the United Nations, sits in the Peace Palace in The Hague.",
    ),
    _choice(
        "Which is the longest river in Europe?",
        ["Volga", "Danube", "Rhine", "Dnieper"],
        ["Volga"],
        "The Volga in Russia is Europe's longest river at about 3,500 km; the Danube comes second.",
    ),
    # Which of these: records
    _choice(
        "Which country was the first to give women the right to vote in national elections?",
        ["New Zealand", "United States", "United Kingdom", "Switzerland"],
        ["New Zealand"],
        "New Zealand gave women the vote in 1893. Switzerland followed only in 1971.",
    ),
    _choice(
        "Which of these game consoles was released first?",
        ["PlayStation", "Nintendo 64", "Dreamcast", "Xbox"],
        ["PlayStation"],
        "The PlayStation came out in 1994, before the Nintendo 64 (1996), the Dreamcast (1998) and the Xbox (2001).",
    ),
    # Odd one out
    _choice(
        "Odd one out: which of these is not a planet?",
        ["Mercury", "Venus", "Ganymede", "Mars", "Neptune"],
        ["Ganymede"],
        "Ganymede is a moon of Jupiter, the largest moon in the solar system; the other four are planets.",
    ),
    _choice(
        "Which of these films was not directed by Steven Spielberg?",
        ["Jaws", "E.T.", "Titanic", "Jurassic Park"],
        ["Titanic"],
        "Titanic (1997) was directed by James Cameron; the other three are Spielberg films.",
    ),
    # Select all that apply
    _choice(
        "Which of these countries lie on the equator?",
        ["Ecuador", "Kenya", "Egypt", "Indonesia", "India"],
        ["Ecuador", "Kenya", "Indonesia"],
        "The equator crosses Ecuador, Kenya and Indonesia. Egypt and India lie entirely north of it.",
    ),
    _choice(
        "Which of these films were directed by Christopher Nolan?",
        ["Inception", "Avatar", "Interstellar", "Gladiator", "The Dark Knight"],
        ["Inception", "Interstellar", "The Dark Knight"],
        "Nolan directed Inception, Interstellar and The Dark Knight. Avatar is by James Cameron, Gladiator by Ridley Scott.",
    ),
    _choice(
        "Which of these elements are noble gases?",
        ["Helium", "Nitrogen", "Neon", "Oxygen"],
        ["Helium", "Neon"],
        "Helium and neon are noble gases, which hardly react with anything. Nitrogen and oxygen are not.",
    ),
    _choice(
        "Which of these cities are national capitals?",
        ["Sydney", "Ottawa", "Istanbul", "Wellington", "Rio de Janeiro"],
        ["Ottawa", "Wellington"],
        "Ottawa is the capital of Canada and Wellington of New Zealand. The other three are famous, but not capitals.",
    ),
    # Sorting (order)
    _order(
        "Sort these companies by founding year, oldest first.",
        ["Google", "Microsoft", "Apple"],
        ["Microsoft", "Apple", "Google"],
        "Microsoft was founded in 1975, Apple in 1976 and Google in 1998.",
    ),
    _order(
        "Sort these by the year they began, earliest first.",
        ["World War I", "Cold War", "French Revolution"],
        ["French Revolution", "World War I", "Cold War"],
        "The French Revolution began in 1789, World War I in 1914 and the Cold War after 1945.",
    ),
]

EXAMPLES: list[Example] = [*FREE_EXAMPLES, *CHOICE_EXAMPLES]


# Models write far more true claims than false ones when left to choose, so the code
# picks the side per request.
FALSE_CLAIM_SHARE = 0.7
FALSE_CLAIM_HINT = "If you write a true or false question, the claim must be false."
TRUE_CLAIM_HINT = "If you write a true or false question, the claim must be true."
# (false claim hint, true claim hint) by language.
CLAIM_HINTS: dict[str, tuple[str, str]] = {
    "en": (FALSE_CLAIM_HINT, TRUE_CLAIM_HINT),
    "de": (
        "Wenn du eine Wahr-oder-falsch-Frage schreibst, muss die Behauptung falsch sein.",
        "Wenn du eine Wahr-oder-falsch-Frage schreibst, muss die Behauptung wahr sein.",
    ),
}


def pick_true_false_hint(rng: random.Random | None = None, language: str = "en") -> str:
    draw = (rng or random).random()
    false_hint, true_hint = CLAIM_HINTS.get(language, CLAIM_HINTS["en"])
    return false_hint if draw < FALSE_CLAIM_SHARE else true_hint


def format_example(example: Example) -> str:
    """An example as the JSON object the model is asked to write."""
    return json.dumps(example, ensure_ascii=False, indent=1)


# The intro of the example block by language. The examples themselves stay English.
EXAMPLE_INTROS: dict[str, str] = {
    "en": (
        "Two examples of good questions, one for each kind of answer format. Let their style "
        "inspire you, but do not copy their topics; your question is about the facts below:"
    ),
    "de": (
        "Zwei Beispiele für gute Fragen, eines für jedes Antwortformat. Lass dich vom Stil "
        "inspirieren, aber übernimm nicht ihre Themen; deine Frage handelt von den Fakten "
        "unten. Beispiele und Fakten sind auf Englisch, deine Frage ist auf Deutsch:"
    ),
}


def pick_examples(rng: random.Random | None = None, language: str = "en") -> str:
    """The example block of a request: one free and one choice example, in random order."""
    source = rng or random
    picked = [source.choice(FREE_EXAMPLES), source.choice(CHOICE_EXAMPLES)]
    source.shuffle(picked)
    examples = "\n\n".join(format_example(example) for example in picked)
    return f"{EXAMPLE_INTROS.get(language, EXAMPLE_INTROS['en'])}\n\n{examples}"


PROMPT = PromptTemplate(
    name="generate_question",
    system=SYSTEM_PROMPT,
    user_template=USER_TEMPLATE,
    localized_user_templates={"de": USER_TEMPLATE_DE},
)
