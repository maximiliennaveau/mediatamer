import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

from mediatamer.ai import run_ai


@dataclass
class CastProfile:
    credits_names: List[str] = field(default_factory=list)
    fictional_characters: List[str] = field(default_factory=list)
    show_name_hints: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "credits_names": self.credits_names,
            "fictional_characters": self.fictional_characters,
            "show_name_hints": self.show_name_hints,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CastProfile":
        if not data:
            return cls()
        show_hints = data.get("show_name_hints", [])
        if isinstance(show_hints, str):
            show_hints = [show_hints]
        # Backward compat: old caches used real_actors + crew_names
        credits = data.get("credits_names") or (
            data.get("real_actors", []) + data.get("crew_names", [])
        )
        return cls(
            credits_names=credits,
            fictional_characters=data.get("fictional_characters", []),
            show_name_hints=show_hints,
            confidence=data.get("confidence", 0.0),
        )


def extract_cast_from_subtitles(subtitle_text: str, config: dict) -> CastProfile:
    """
    Extracts cast, character, crew, and show name hints from subtitle text
    using an LLM.
    """
    if not subtitle_text or not subtitle_text.strip():
        return CastProfile()

    prompt = _build_cast_prompt(subtitle_text)
    response = run_ai(prompt, config, json_mode=True)
    try:
        data = json.loads(response)
        return CastProfile.from_dict(data)
    except Exception as e:
        print(f"[Cast Extractor] Error parsing LLM JSON: {e}")
        return CastProfile()


def _build_cast_prompt(text: str) -> str:
    """Build the shared LLM prompt for credits name extraction."""
    return f"""You are a media credits parser. Extract all real human beings and the show title from raw OCR text from video credits.

RULES:

1. credits_names — ALL real individual human beings mentioned in the credits:
   - Actors, voice actors, directors, producers, composers, writers, editors, cinematographers, any crew.
   - Do NOT include fictional character names, organization names, or brand names (DivX, Dolby, BBC, etc.).
   - TV credits often list a CHARACTER NAME on one line then the ACTOR on the very next line:
       Prentis
       PAUL KAYE
     → Include "Paul Kaye", not "Prentis".
   - French dub format "Bennett  Olivier Prémel" means character "Bennett" voiced by "Olivier Prémel" — include only "Olivier Prémel".
   - Include ALL people found — guest cast, supporting roles, and crew are all equally important.

2. fictional_characters — ONLY story character names (e.g. "The Doctor", "Prentis", "Walter White").
   Do NOT include real people or organizations here.

3. show_name_hints — The primary display title of the show or film. Return a list of strings.

4. confidence — integer 0–100 reflecting your extraction confidence.

Return ONLY a valid JSON object with exactly these keys:
credits_names, fictional_characters, show_name_hints, confidence.
No extra text, no markdown.

### RAW OCR TEXT:
{text}
"""
