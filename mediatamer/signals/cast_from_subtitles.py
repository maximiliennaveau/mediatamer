import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

from mediatamer.ai import run_ai


@dataclass
class CastProfile:
    fictional_characters: List[str] = field(default_factory=list)
    real_actors: List[str] = field(default_factory=list)
    crew_names: List[str] = field(default_factory=list)
    producers_and_funders: List[str] = field(default_factory=list)
    show_name_hints: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fictional_characters": self.fictional_characters,
            "real_actors": self.real_actors,
            "crew_names": self.crew_names,
            "producers_and_funders": self.producers_and_funders,
            "show_name_hints": self.show_name_hints,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CastProfile":
        if not data:
            return cls()
        # show_name_hints may come back as a plain string from some LLM responses
        show_hints = data.get("show_name_hints", [])
        if isinstance(show_hints, str):
            show_hints = [show_hints]
        return cls(
            fictional_characters=data.get("fictional_characters", []),
            real_actors=data.get("real_actors", []),
            crew_names=data.get("crew_names", []),
            producers_and_funders=data.get("producers_and_funders", []),
            show_name_hints=show_hints,
            confidence=data.get("confidence", 0.0),
        )


def extract_cast_from_subtitles(subtitle_text: str) -> CastProfile:
    """
    Extracts cast, character, crew, and show name hints from subtitle text
    using an LLM.
    """
    if not subtitle_text or not subtitle_text.strip():
        return CastProfile()

    prompt = f"""
You are a media credits parser. Your job is to classify names from raw OCR text extracted from video credits.

STRICT CLASSIFICATION RULES — read carefully before assigning any name:

1. fictional_characters:
   - ONLY names of story characters that appear in the narrative (e.g. "Walter White", "Sherlock Holmes", "Sintel").
   - Do NOT include real person names here, even if they appear alongside character names.
   - Do NOT include production company names, sponsors, or technology/brand names (e.g. "DivX", "Dolby" are NOT characters).

2. real_actors:
   - ONLY real human beings who perform in the show/film (voice actors accepted).
   - These are the people listed next to character names, or in the cast section.
   - Do NOT include directors, editors, composers, or other crew here.
   - Do NOT include organization names (e.g. "Blender Foundation" is NOT an actor).

3. crew_names:
   - Real individual HUMAN BEINGS who worked behind the camera: directors, producers, composers, writers, editors, cinematographers.
   - Do NOT include company or organization names here.
   - If you are unsure whether a name belongs in real_actors or crew_names, prefer crew_names.

4. producers_and_funders:
   - Names of production companies, studios, foundations, funds, or sponsors that provided financial or production support.
   - These are ORGANIZATIONS, not people (e.g. "Blender Foundation", "Netherlands Film Fund").

5. show_name_hints:
   - The primary display title of the show or film (e.g. "Sintel", "Doctor Who").
   - Do NOT use project codenames, subtitles, or descriptions (e.g. "The Durian Open Movie Project" is a codename, NOT a title).
   - Return a list of strings.

6. confidence: integer 0-100 reflecting your overall confidence in the extraction quality.

IMPORTANT DISAMBIGUATION TIPS:
- Brand names (DivX, Dolby, IMAX, etc.) are NEVER people — omit them from all person fields.
- A name appearing on its own line, in ALL CAPS, as the only text, is more likely a title than a character.
- Names preceded by "PRESENTS", "FOUNDATION", "INSTITUTE", "FUND", "PROJECT" are organizations.
- Names preceded by "DIRECTED BY", "MUSIC BY", "EDITED BY", "PRODUCED BY" are individual crew members.
- Names appearing between dashes (e.g. "ALICE SMITH - BOB JONES") are typically cast or crew pairs.

Return ONLY a valid JSON object with exactly these keys:
fictional_characters, real_actors, crew_names, producers_and_funders, show_name_hints, confidence.
No extra text, no markdown.

### RAW OCR TEXT:
{subtitle_text}
"""

    response = run_ai(prompt, json_mode=True)
    try:
        data = json.loads(response)
        return CastProfile.from_dict(data)
    except Exception as e:
        print(f"[Cast Extractor] Error parsing LLM JSON: {e}")
        return CastProfile()
