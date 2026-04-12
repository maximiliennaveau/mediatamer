import json
import inspect
from typing import List, Dict, Any
from mediatamer.config import load_config
from mediatamer.signals.tmdb import fetch_tmdb_episodes, fetch_tmdb_person_credits
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
        sub_text = meta.subtitles or ""
        search_history = []
        max_iterations = 4
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[AI Agent Loop] Iteration {iteration}/{max_iterations}...")

            prompt = self._build_agentic_prompt(meta, search_history)

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
            q_type = q.get("type", "SEARCH_EPISODES")

            if q_type == "SEARCH_PERSON":
                name = q.get("name")
                if not name:
                    continue
                print(f"     Fetching TMDB for Person '{name}'")
                credits = fetch_tmdb_person_credits(name, self.tmdb_api_key)

                # Keep top 15 to avoid huge context
                filtered_credits = credits[:15]
                results.append(
                    {
                        "query": {"type": "SEARCH_PERSON", "name": name},
                        "results_count": len(filtered_credits),
                        "credits": filtered_credits,
                    }
                )
            else:
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
        meta: VideoMetadata,
        search_history: List[Dict],
    ) -> str:
        """
        Builds a structured, agentic prompt for the AI Video Matcher.
        Using inspect.cleandoc to ensure clean formatting without leading whitespace.
        """
        # 1. Identity and Core Instructions
        identity = inspect.cleandoc("""
            # IDENTITY
            You are an Autonomous Media Identification Agent. Your goal is to identify the EXACT TV show, season, and episode 
            for the provided video file. You operate in an iterative loop, using results from previous database searches 
             to refine your identification.
        """)

        # 2. File and Technical Evidence
        # We include the full path because it often contains a parent folder named after the show.
        evidence_data = {
            "full_path": str(meta.path),
            "filename": meta.path.name,
            "duration_sec": meta.technical.duration if meta.technical else None,
            "heuristics_guess": meta.heuristics,
            "guessit_analysis": meta.guessit,
            "ai_filename_guess": meta.ai_guess,
            "opensubtitles_match": meta.opensubtitles
        }

        evidence_file = inspect.cleandoc(f"""
            ## EVIDENCE: FILE SYSTEM & TECHNICAL
            {json.dumps(evidence_data, indent=2)}
        """)

        # 3. Content-based Evidence (Subtitles & Cast)
        # Summary and cast profiles are high-confidence signals extracted from the video content itself.
        summary_content = meta.summary.get("summary", "No summary available.") if isinstance(meta.summary, dict) else str(meta.summary)
        
        evidence_content = inspect.cleandoc(f"""
            ## EVIDENCE: CONTENT ANALYSIS
            ### SUBTITLE SUMMARY
            {summary_content}

            ### CAST PROFILE
            {json.dumps(meta.cast_profile, indent=2)}
        """)

        # 4. Search Commands
        commands = inspect.cleandoc("""
            ## AVAILABLE SEARCH COMMANDS
            To gather more information, return a JSON object with status "SEARCHING".
            
            1. **SEARCH_EPISODES**: Fetch episode lists and overviews for a show. 
               - Use "season: 0" for Specials/Movies/OVA.
               - Example: {"type": "SEARCH_EPISODES", "show": "Doctor Who", "season": 0}

            2. **SEARCH_PERSON**: Look up actor/crew credits. 
               - Use names from the Cast Profile to disambiguate similar titles.
               - Example: {"type": "SEARCH_PERSON", "name": "Bryan Cranston"}
        """)

        # 5. Output Format
        output_format = inspect.cleandoc("""
            ## OUTPUT FORMAT
            - Return ONLY valid JSON.
            - Provide a "reasoning" field explaining your strategy.
            - If found: { "status": "FOUND", "show": "...", "season": X, "episode": Y, "title": "...", "confidence_score": 0-100 }
            - If searching: { "status": "SEARCHING", "queries": [...] }
        """)

        # 6. History
        history_section = inspect.cleandoc(f"""
            ## PREVIOUS SEARCH RESULTS
            {json.dumps(search_history, indent=2) if search_history else "No searches performed yet."}
        """)

        # Assemble final prompt
        prompt = "\n\n".join([
            identity,
            evidence_file,
            evidence_content,
            commands,
            output_format,
            history_section
        ])

        return prompt
