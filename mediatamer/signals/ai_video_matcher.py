import json
from typing import List, Dict, Any
from mediatamer.config import load_config
from mediatamer.signals.tmdb import fetch_tmdb_episodes
from mediatamer.signals.tvdb import fetch_tvdb_info
from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.scoring import score_episode_match


def match_episode(meta: VideoMetadata) -> None:
    matcher = AIVideoMatcher()
    matcher.match(meta)


class AIVideoMatcher:
    def __init__(self):
        self.config = load_config()
        self.tmdb_api_key = self.config.get("tmbd-api-key")
        self.tvdb_api_key = self.config.get("tvdb-api-key")

    def match(self, meta: VideoMetadata) -> None:
        print(f"[AI Episode Matcher] Analyzing iteratively: {meta.path.name}")
        tech_data = meta.technical.to_dict() if meta.technical else {}
        sub_text = meta.subtitles or ""

        guess = {
            "guessit": meta.guessit,
            "heuristics": meta.heuristics,
        }
        search_history = []
        max_iterations = 4
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[AI Agent Loop] Iteration {iteration}/{max_iterations}...")

            prompt = self._build_agentic_prompt(
                meta.path.name, guess, tech_data, sub_text, search_history
            )

            # Note: We must ensure JSON format from the AI.
            response = run_ai(prompt, json_mode=True)

            try:
                action = json.loads(response)
            except Exception as e:
                print(f"[AI Agent Loop] JSON Parsing Error: {e}")
                meta.ai_match = {"error": f"Failed to parse LLM response: {e}"}
                break

            status = action.get("status")
            reasoning = action.get("reasoning", "No reasoning provided.")
            print(f"  -> AI Status: {status}")
            print(f"  -> AI Reasoning: {reasoning}")

            if status == "FOUND":
                show = action.get("show")
                season = action.get("season")
                episode_num = action.get("episode")
                title = action.get("title")

                # Verify with scoring to be safe
                print(
                    f"  -> Trying to verify AI's final answer: {show} S{season}E{episode_num}"
                )
                _, season_episodes = fetch_tmdb_episodes(
                    show, season, self.tmdb_api_key
                )
                target_ep = next(
                    (
                        ep
                        for ep in season_episodes
                        if ep.get("episode_number") == episode_num
                    ),
                    None,
                )

                if target_ep:
                    score_res = score_episode_match(
                        target_ep,
                        meta.path,
                        meta.technical,
                        sub_text=sub_text,
                        context_hints={
                            "is_likely_episode": True,
                            "season_number": season,
                        },
                    )
                    final_score = score_res["score"]
                    print(f"  -> Verification Score: {final_score}")

                    meta.ai_match = {
                        "show": show,
                        "season": season,
                        "episode": episode_num,
                        "title": title or target_ep.get("name"),
                        "best_candidate": target_ep,
                        "score": final_score,
                        "reasoning": reasoning + f" (Verified Score: {final_score})",
                        "ai_full_response": action,
                        "phase": f"agent_found_iter_{iteration}",
                    }
                else:
                    print(
                        "  -> Could not locate the episode in TMDB to verify. Accepting blind AI response."
                    )
                    meta.ai_match = {
                        "show": show,
                        "season": season,
                        "episode": episode_num,
                        "title": title,
                        "score": action.get("confidence_score", 0.0),
                        "reasoning": reasoning,
                        "ai_full_response": action,
                        "phase": f"agent_found_unverified_iter_{iteration}",
                    }
                break

            elif status == "SEARCHING":
                queries = action.get("queries", [])
                if not queries:
                    print(
                        "  -> AI returned SEARCHING but provided no queries. Stopping."
                    )
                    break

                print(f"  -> Executing {len(queries)} queries...")
                print(f"  -> Queries: {queries}")
                history_entry = self._execute_search_queries(queries)
                search_history.extend(history_entry)

            else:
                print(f"  -> Unknown status '{status}'. Stopping.")
                break
        else:
            print("[AI Agent Loop] Max iterations reached without finding a match.")
            meta.ai_match = {
                "error": "Max iterations reached without finding an episode."
            }

    def initial_guess(self, meta: VideoMetadata) -> Dict:
        guess_heuristic = meta.heuristics
        guess_guessit = meta.guessit
        tech_data = meta.technical.to_dict() if meta.technical else {}
        sub_text = meta.subtitles or ""

        if not guess_heuristic or not guess_guessit or not tech_data or not sub_text:
            print("[AI Episode Matcher] Missing required signals. Skipping.")
            return

        initial_show_guess = [
            guess_heuristic.get("show"),
            guess_guessit.get("show"),
        ]
        initial_show_guess = [show for show in initial_show_guess if show]

        initial_season_guess = [
            guess_heuristic.get("season"),
            guess_guessit.get("season"),
        ]
        initial_season_guess = [season for season in initial_season_guess if season]

        return initial_show_guess, initial_season_guess

    @staticmethod
    def _resolve_season(season) -> int:
        """Map a season value (int or string alias) to a season int.
        Season 0 = Specials in TMDB convention.
        """
        if isinstance(season, int):
            return season
        alias = str(season).lower().strip()
        SPECIALS_ALIASES = {
            "specials",
            "special",
            "christmas special",
            "christmas specials",
            "extras",
            "bonus",
            "ova",
            "movie specials",
            "0",
        }
        if any(a in alias for a in SPECIALS_ALIASES):
            return 0
        # Try parsing as a bare number
        try:
            return int(alias)
        except ValueError:
            # Last resort: unknown alias → treat as Season 0 with a warning
            print(
                f"     [Warning] Unknown season alias '{season}', defaulting to Season 0"
            )
            return 0

    def _execute_search_queries(
        self, queries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        results = []
        for q in queries:
            sh = q.get("show")
            se_raw = q.get("season")
            if not sh or se_raw is None:
                continue
            se = self._resolve_season(se_raw)

            print(f"     Fetching TMDB & TVDB for '{sh}' Season {se} (raw: '{se_raw}')")
            # Fetch TMDB
            _, tmdb_eps = fetch_tmdb_episodes(sh, se, self.tmdb_api_key)
            # Fetch TVDB (which user redirected to API basically)
            _, tvdb_eps = fetch_tvdb_info(sh, se, self.tvdb_api_key)

            # Combine distinct
            combined_hash = {}
            for ep in tmdb_eps + tvdb_eps:
                ep_id = ep.get("episode_number")
                if ep_id and ep_id not in combined_hash:
                    combined_hash[ep_id] = {
                        "episode_number": ep_id,
                        "name": ep.get("name"),
                        "overview": ep.get("overview"),
                        "runtime_min": ep.get("runtime"),
                        "guest_stars": [
                            g.get("name") for g in ep.get("guest_stars", [])[:3]
                        ],
                    }

            filtered_eps = list(combined_hash.values())
            results.append(
                {
                    "query": {"show": sh, "season": se},
                    "results_count": len(filtered_eps),
                    "episodes": filtered_eps,
                }
            )
        return results

    def _build_agentic_prompt(
        self,
        filename: str,
        guess: Dict,
        tech: Dict,
        subtitles: str,
        search_history: List[Dict],
    ) -> str:
        video_metadata = {
            "filename": filename,
            "heuristics_guess": guess,
            "duration_sec": tech.get("duration"),
        }

        # Cap subtitles so it isn't too huge
        subtitles_snip = subtitles[:8000] if len(subtitles) > 8000 else subtitles

        prompt = f"""You are an elite TV series database assistant acting as an autonomous search agent.
Your objective is to identify the EXACT TV show, season, and episode based strictly on the provided subtitle snippet and metadata.

### VIDEO FILE METADATA
{json.dumps(video_metadata, indent=2)}

### SUBTITLE CONTENT
---
{subtitles_snip}
---

### SEARCH HISTORY AND DATABASE RESULTS
{json.dumps(search_history, indent=2)}

### YOUR INSTRUCTIONS
You operate in a loop. You can either search the database for candidate episodes, or declare you have definitively found the match. Only use "season: 0" to search for Specials (like Christmas specials or bonus episodes).

IF you need to see episode summaries for a specific show and season to find a match, return a JSON object with status "SEARCHING".
The "season" field inside each query can be an INTEGER (e.g. 9) or a STRING ALIAS (e.g. "Specials", "Christmas Special", "Extras").
Examples: {{"show": "Doctor Who", "season": 0}}, {{"show": "Doctor Who", "season": "Christmas Special"}}, {{"show": "Doctor Who", "season": 9}}
{{
  "status": "SEARCHING",
  "reasoning": "The dialogue hints at a Christmas special. I should check the Specials season of Doctor Who.",
  "queries": [
    {{"show": "Doctor Who", "season": "Christmas Special"}},
    {{"show": "Doctor Who", "season": 0}}
  ]
}}
Wait for me to run the query and provide the results in the next iteration.

IF you are absolutely certain you have found the matching episode because the subtitle dialogue clearly aligns with one of the episode 'overviews' in your SEARCH HISTORY, return a JSON object with status "FOUND":
{{
  "status": "FOUND",
  "reasoning": "The dialogue matches 'Last Christmas' perfectly from the Season 0 search results.",
  "show": "Doctor Who",
  "season": 0,
  "episode": 142,
  "title": "Last Christmas",
  "confidence_score": 95.0
}}

IMPORTANT: Return ONLY valid JSON format. Provide nothing else outside of the JSON block. Do not use markdown wrappers.
"""
        return prompt
