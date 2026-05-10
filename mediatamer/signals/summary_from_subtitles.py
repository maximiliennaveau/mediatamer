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

    prompt = f"""You are a TV/film analyst. Read the subtitle text below and return a JSON object with exactly this key:

- "summary": a 12 sentence synopsis IN English, present tense, third person, covering the main plot points in chronological order. Write it like an editorial description on TMDB/TVDB — specific enough to identify the episode uniquely. Naturally include key identifying terms: character names, place names, city names, location types, factions, races, organizations, or any other proper nouns that appear in the subtitles and help distinguish this story.

Rules: return ONLY valid JSON, no markdown, no extra text. All strings IN ENGLISH. Do not invent events not supported by the subtitles.

SUBTITLE TEXT:
{metadata.subtitles}
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
