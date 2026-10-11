"""Languages the game can be played in.

The language decides in which language questions are written. UI texts are translated in
the frontend (src/strings.ts).
"""

from typing import Literal

Language = Literal["en", "de"]
DEFAULT_LANGUAGE: Language = "en"
