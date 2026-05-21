import json
from typing import TYPE_CHECKING, Dict

from mediatamer.ai import run_ai

if TYPE_CHECKING:
    from mediatamer.signals.video_metadata import VideoMetadata


def extract_summary_from_subtitles(metadata: "VideoMetadata", config: dict) -> Dict:
    """
    Extracts a structured summary from subtitles and populates the metadata.
    Returns the extracted SummaryFromSubtitle object.
    """
    if not metadata.subtitles or not metadata.subtitles.strip():
        metadata.summary = dict()
        return dict()

    # Truncate subtitle text to avoid exceeding the model context window.
    # num_ctx defaults to 16384 tokens (~65000 chars); reserve ~12000 chars for
    # the prompt template and the JSON output, leaving ~53000 chars for subtitles.
    _MAX_SUBTITLE_CHARS = 53_000
    subtitle_text = metadata.subtitles
    if len(subtitle_text) > _MAX_SUBTITLE_CHARS:
        subtitle_text = subtitle_text[:_MAX_SUBTITLE_CHARS]

    prompt = f"""You are a TV/film analyst. The subtitles may be in any language. \
YOUR RESPONSE MUST ALWAYS BE IN ENGLISH — translate if needed.

Read the subtitle text below and return a JSON object with exactly this key:

- "summary": a 12-sentence synopsis written in ENGLISH, present tense, third person, \
covering the main plot points in chronological order. Write it like an editorial description \
on TMDB/TVDB — specific enough to identify the episode uniquely. Naturally include key \
identifying terms: character names, place names, location types, factions, races, \
organizations, or any other proper nouns that appear in the subtitles and help distinguish \
this story.

CRITICAL RULES:
- The "summary" value MUST be written in ENGLISH regardless of the subtitle language.
- Return ONLY valid JSON, no markdown, no extra text.
- Do not invent events not supported by the subtitles.

SUBTITLE TEXT:
{subtitle_text}
    """

    json_response = run_ai(prompt, config, json_mode=True)
    try:
        response = json.loads(json_response)
    except Exception as e:
        print(f"[Summary Extractor] Error parsing LLM JSON: {e}")
        metadata.summary = {}
        return {}

    metadata.summary = {
        "summary": response.get("summary", ""),
    }
    return metadata.summary
