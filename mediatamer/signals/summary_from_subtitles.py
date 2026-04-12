import json
from dataclasses import dataclass, field
from typing import List, Dict, Any

from mediatamer.ai import run_ai


@dataclass
class CharacterEntry:
    name: str = ""
    role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "role": self.role}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterEntry":
        return cls(name=data.get("name", ""), role=data.get("role", ""))


@dataclass
class SummaryFromSubtitle:
    """Structured episode/film summary extracted from subtitle text.

    Designed to be compared against TMDB / TVDB episode descriptions.
    """

    summary: str = ""
    main_characters: List[CharacterEntry] = field(default_factory=list)
    secondary_characters: List[CharacterEntry] = field(default_factory=list)
    plot_points: List[str] = field(default_factory=list)
    plot_twists: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    tone: str = ""
    setting: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "main_characters": [c.to_dict() for c in self.main_characters],
            "secondary_characters": [c.to_dict() for c in self.secondary_characters],
            "plot_points": self.plot_points,
            "plot_twists": self.plot_twists,
            "themes": self.themes,
            "tone": self.tone,
            "setting": self.setting,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryFromSubtitle":
        if not data:
            return cls()

        def _parse_chars(raw: Any) -> List[CharacterEntry]:
            if not isinstance(raw, list):
                return []
            result = []
            for item in raw:
                if isinstance(item, dict):
                    result.append(CharacterEntry.from_dict(item))
                elif isinstance(item, str):
                    result.append(CharacterEntry(name=item))
            return result

        return cls(
            summary=data.get("summary", "") if isinstance(data.get("summary"), str) else "",
            main_characters=_parse_chars(data.get("main_characters", [])),
            secondary_characters=_parse_chars(data.get("secondary_characters", [])),
            plot_points=data.get("plot_points", []) if isinstance(data.get("plot_points"), list) else [],
            plot_twists=data.get("plot_twists", []) if isinstance(data.get("plot_twists"), list) else [],
            themes=data.get("themes", []) if isinstance(data.get("themes"), list) else [],
            tone=data.get("tone", "") if isinstance(data.get("tone"), str) else "",
            setting=data.get("setting", "") if isinstance(data.get("setting"), str) else "",
            confidence=float(data.get("confidence", 0.0)),
        )


def extract_summary_from_subtitles(subtitle_text: str) -> SummaryFromSubtitle:
    """
    Extracts summary from subtitle text using an LLM.
    """
    if not subtitle_text or not subtitle_text.strip():
        return SummaryFromSubtitle()

    prompt = f"""
You are an expert TV/film analyst. Your job is to read subtitle text from a single episode or film and produce a
structured episode summary that can be compared against official databases like TMDB or TVDB.

Your output will be used programmatically, so follow every rule below with precision.

---

## TASK

Analyse the subtitles and return a JSON object with the following fields:

### 1. `summary` (string, REQUIRED)
A **2–5 sentence synopsis** of the episode/film written in the **present tense**, third person.
- Describe the main events in chronological order.
- Write it as a concise editorial summary, similar to what you would find on TMDB or TVDB.
- Do NOT mention the subtitles or the word "episode" explicitly — write as if describing the story directly.
- Avoid spoiling mid/late twists in the opening sentence; build up to them naturally.

### 2. `main_characters` (list of objects, REQUIRED)
List the **most prominent characters** who drive the plot. Each object:
```
{{ "name": "<character name>", "role": "<brief role description, 1 sentence max>" }}
```
- Include 1–5 characters maximum.
- Use character names (not actor names).
- "role" should describe what they do in THIS episode, not their general role in the series.

### 3. `secondary_characters` (list of objects)
List **supporting characters** who appear but are not central to the main plot. Same format as `main_characters`.
- Include 0–5 characters maximum.
- Omit characters with no discernible role (e.g. background crowd, unnamed voices).

### 4. `plot_points` (list of strings)
An **ordered list of key plot events**, written as concise bullet facts (one sentence each).
- List 3–10 events maximum.
- Stay chronological.
- Focus on story-driving events, not every line of dialogue.

### 5. `plot_twists` (list of strings)
List any **surprising revelations, unexpected turns, or dramatic reversals** that occur.
- An empty list `[]` is acceptable if no twists are present.
- Each twist should be a single sentence.

### 6. `themes` (list of strings)
2–5 **thematic keywords or short phrases** (e.g. "redemption", "loss of innocence", "betrayal", "found family").

### 7. `tone` (string)
One or two words describing the overall tone of the episode (e.g. "dark and tense", "lighthearted", "melancholic", "action-packed").

### 8. `setting` (string)
A brief description of the primary location(s) and time period of the episode (e.g. "medieval fantasy world", "modern-day New York City, present day").

### 9. `confidence` (integer 0–100)
Your overall confidence in the quality of this extraction, based on subtitle completeness and clarity.
- 90–100: Rich, complete subtitles with clear dialogue.
- 60–89: Subtitles present but partial, or some dialogue is ambiguous.
- 30–59: Sparse subtitles, heavy reliance on inference.
- 0–29: Barely enough to extract anything meaningful.

---

## OUTPUT RULES

- Return ONLY a valid JSON object. No markdown, no code fences, no commentary before or after.
- All string values must be in English.
- If a field cannot be determined from the subtitles, return an empty list `[]` for list fields, or an empty string `""` for string fields — never omit a key.
- Character names must match how they appear in the subtitles (do not substitute actor names).
- Do NOT invent plot points that are not supported by the subtitle text.

### REQUIRED JSON KEYS:
summary, main_characters, secondary_characters, plot_points, plot_twists, themes, tone, setting, confidence

---

### SUBTITLE TEXT:
{subtitle_text}
"""

    response = run_ai(prompt, json_mode=True)
    try:
        data = json.loads(response)
        return SummaryFromSubtitle.from_dict(data)
    except Exception as e:
        print(f"[Summary Extractor] Error parsing LLM JSON: {e}")
        return SummaryFromSubtitle()
