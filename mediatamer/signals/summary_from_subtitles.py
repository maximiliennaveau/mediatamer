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

    prompt = f"""
    You are an expert TV/film analyst. Your job is to read subtitle text from a single episode or film and produce a
    structured episode summary that can be compared against official databases like TMDB or TVDB.

    Your output will be used programmatically, so follow every rule below with precision.

    ---

    ## TASK

    Analyse the subtitles and return a JSON object with the following fields:

    ### 1. `summary` (string, REQUIRED)
    A **2-5 sentence synopsis** of the episode/film written in the **present tense**, third person.
    - Describe the main events in chronological order.
    - Write it as a concise editorial summary, similar to what you would find on TMDB or TVDB.
    - Do NOT mention the subtitles or the word "episode" explicitly — write as if describing the story directly.
    - Avoid spoiling mid/late twists in the opening sentence; build up to them naturally.

    ### 2. `main_characters` (list of objects, REQUIRED)
    List the **most prominent characters** who drive the plot. Each object:
    ```
    {{ "name": "<character name>", "role": "<brief role description, 1 sentence max>" }}
    ```
    - Include 1-5 characters maximum.
    - Use character names (not actor names).
    - "role" should describe what they do in THIS episode, not their general role in the series.

    ### 3. `secondary_characters` (list of objects)
    List **supporting characters** who appear but are not central to the main plot. Same format as `main_characters`.
    - Include 0-5 characters maximum.
    - Omit characters with no discernible role (e.g. background crowd, unnamed voices).

    ### 4. `confidence` (integer 0-100)
    Your overall confidence in the quality of this extraction, based on subtitle completeness and clarity.
    - 90-100: Rich, complete subtitles with clear dialogue.
    - 60-89: Subtitles present but partial, or some dialogue is ambiguous.
    - 30-59: Sparse subtitles, heavy reliance on inference.
    - 0-29: Barely enough to extract anything meaningful.

    ---

    ## OUTPUT RULES

    - Return ONLY a valid JSON object. No markdown, no code fences, no commentary before or after.
    - All string values must be in English.
    - If a field cannot be determined from the subtitles, return an empty list `[]` for list fields, or an empty string `""` for string fields — never omit a key.
    - Character names must match how they appear in the subtitles (do not substitute actor names).
    - Do NOT invent plot points that are not supported by the subtitle text.

    ### REQUIRED JSON KEYS:
    summary, main_characters, secondary_characters, confidence

    ---

    ### SUBTITLE TEXT:
    {metadata.subtitles}
    """

    json_response = run_ai(prompt, config, json_mode=True)
    try:
        response = json.loads(json_response)

    except Exception as e:
        raise ValueError(f"[Summary Extractor] Error parsing LLM JSON: {e}")

    metadata.summary = {
        "summary": response["summary"],
        "main_characters": response["main_characters"],
        "secondary_characters": response["secondary_characters"],
        "confidence": response["confidence"],
    }
    return metadata.summary
