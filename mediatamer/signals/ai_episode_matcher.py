import json
from typing import List, Dict
from mediatamer.config import load_config
from mediatamer.signals.tmdb import fetch_tmdb_episodes
from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata


def match_episode(meta: VideoMetadata) -> None:
    """
    Gathers all possible signals from metadata and queries the AI.
    Fills in meta.ai_match.
    """
    matcher = AIEpisodeMatcher()
    matcher.match(meta)


class AIEpisodeMatcher:
    """
    A comprehensive matcher that aggregates all available metadata
    and uses AI to determine the best episode match.
    """

    def __init__(self):
        self.config = load_config()
        self.tmdb_api_key = self.config.get("tmbd-api-key")

    def match(self, meta: VideoMetadata) -> None:
        """
        Gathers all possible signals from metadata and queries the AI.
        Fills in meta.ai_match.
        """
        print(f"[AI Episode Matcher] Analyzing: {meta.path.name}")

        # Extract components for convenience and verify they exist
        guess = meta.guessit
        tech_data = meta.technical.to_legacy_dict() if meta.technical else {}
        sub_text = meta.subtitles or ""

        assert guess, "Guessit analysis is required for AI Episode Matcher"
        assert tech_data, "Technical data is required for AI Episode Matcher"
        assert sub_text, "Subtitle text is required for AI Episode Matcher"

        # Fetch TMDB Candidates
        show_name = guess.get("show")
        season_num = guess.get("season")

        candidates = []
        if show_name and season_num is not None:
            _, candidates = fetch_tmdb_episodes(
                show_name, season_num, self.tmdb_api_key
            )

        if not candidates:
            meta.ai_match = {"error": "No TMDB candidates found for show/season."}
            return

        # 5. Build Comprehensive AI Prompt
        prompt = self._build_prompt(
            meta.path.name, guess, tech_data, sub_text, candidates
        )

        # 6. Run AI
        response = run_ai(prompt)

        try:
            # Clean up response
            clean_res = response.strip()
            if clean_res.startswith("```json"):
                clean_res = clean_res[7:-3].strip()
            elif clean_res.startswith("```"):
                clean_res = clean_res[3:-3].strip()

            match_data = json.loads(clean_res)
            best_id = match_data.get("best_candidate_episode_number")

            # Find the episode object
            best_ep = next(
                (ep for ep in candidates if ep.get("episode_number") == best_id), None
            )

            meta.ai_match = {
                "best_candidate": best_ep,
                "score": match_data.get("confidence_score", 0.0),
                "reasoning": match_data.get("reasoning", ""),
                "ai_full_response": match_data,
            }
        except Exception as e:
            print(f"Holistic Matcher Parse Error: {e}\nResponse: {response}")
            meta.ai_match = {"error": f"Failed to parse AI response: {e}"}

    def _build_prompt(
        self,
        filename: str,
        guess: Dict,
        tech: Dict,
        subtitles: str,
        candidates: List[Dict],
    ) -> str:
        """Constructs the all-encompassing matching prompt."""

        # Format Video Metadata
        video_metadata = {
            "filename": filename,
            "guessit_analysis": guess,
            "technical_specs": {
                "duration_sec": tech.get("duration"),
                "chapter_count": len(tech.get("chapters", [])),
                "embedded_title": tech.get("embedded_title"),
                "file_size": tech.get("mediainfo", {})
                .get("media", {})
                .get("track", [{}])[0]
                .get("FileSize"),
            },
        }

        # Format candidates with relevant cross-reference data
        enriched_candidates = []
        for ep in candidates:
            enriched_candidates.append(
                {
                    "episode_number": ep.get("episode_number"),
                    "name": ep.get("name"),
                    "overview": ep.get("overview"),
                    "runtime_min": ep.get("runtime"),
                    "directors": [
                        c.get("name")
                        for c in ep.get("crew", [])
                        if c.get("job") == "Director"
                    ],
                    "writers": [
                        c.get("name")
                        for c in ep.get("crew", [])
                        if c.get("job") == "Writer"
                    ],
                    "guest_stars": [
                        g.get("name") for g in ep.get("guest_stars", [])[:5]
                    ],
                }
            )

        prompt = f"""You are an elite media archivist. Your goal is to match a video file to its correct TV episode using ALL provided metadata.

### VIDEO FILE SIGNALS
- Filename Metadata: {json.dumps(video_metadata, indent=2)}
- Subtitle Content (First 100k chars):
---
{subtitles}
---

### TMDB CANDIDATE EPISODES
{json.dumps(enriched_candidates, indent=2)}

### INSTRUCTIONS
1. Analyze the filename, technical specs (duration vs runtime), and subtitle content.
2. Cross-reference subtitle dialogue, names mentioned, or themes with episode overviews and credits.
3. Identify which candidate is the most likely match.

Return a JSON object with:
- "best_candidate_episode_number": (int) The episode number.
- "confidence_score": (float) 0.0 to 1.0.
- "reasoning": (string) Brief explanation of why it matches (e.g. "Dialog mentioned character X", "Duration matches perfectly").

Only return the JSON object."""
        return prompt
