import json
import inspect
from typing import List, Dict, Any, Optional
from mediatamer.config import load_config
from mediatamer.signals.tmdb import fetch_tmdb_episodes, fetch_tmdb_person_credits
from mediatamer.signals.tvdb import fetch_tvdb_info
from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.scoring import score_episode_match


def match_episode(meta: VideoMetadata, config: dict) -> None:
    matcher = AIVideoMatcher()
    matcher.match(meta, config)


class AIVideoMatcher:
    def __init__(self):
        self.config = load_config()
        self.tmdb_api_key = self.config.get("tmdb-api-key")
        self.tvdb_api_key = self.config.get("tvdb-api-key")

    def match(self, meta: VideoMetadata, config: dict) -> None:
        self.config = config
        self.tmdb_api_key = self.config.get("tmdb-api-key")
        self.tvdb_api_key = self.config.get("tvdb-api-key")

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
            response = run_ai(prompt, config, json_mode=True)

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
                            "is_likely_episode": meta.heuristics.get("is_episode"),
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
                target_dur = meta.technical.duration if meta.technical else None
                history_entry = self._execute_search_queries(queries, target_dur)
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
        self, queries: List[Dict[str, Any]], target_duration_sec: Optional[float] = None
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

                # Keep top 15 to avoid huge context, truncate overviews
                filtered_credits = []
                for cr in credits[:15]:
                    ov = cr.get("overview", "")
                    cr["overview"] = (ov[:200] + "...") if len(ov) > 200 else ov
                    filtered_credits.append(cr)

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

            # Combine distinct, truncate overviews, and filter by duration
            combined_hash = {}
            for ep in tmdb_eps + tvdb_eps:
                ep_id = ep.get("episode_number")
                if ep_id and ep_id not in combined_hash:
                    # Duration check (tolerance: +/- 15 mins)
                    ep_dur_min = ep.get("runtime")
                    if target_duration_sec and ep_dur_min:
                        diff = abs((ep_dur_min * 60) - target_duration_sec)
                        if diff > 900:  # 15 minutes
                            # Skip if duration mismatch is too large, unless it's the only hit
                            if len(tmdb_eps + tvdb_eps) > 1:
                                continue

                    ov = ep.get("overview", "")
                    combined_hash[ep_id] = {
                        "episode_number": ep_id,
                        "name": ep.get("name"),
                        "overview": (ov[:200] + "...") if len(ov) > 200 else ov,
                        "runtime_min": ep_dur_min,
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
        # 1. Identity
        identity = """
            # IDENTITY
            You are an Autonomous Media Identification Agent. Your goal is to identify the EXACT TV show, season, and episode 
            for the provided video file. You operate in an iterative loop, using results from previous database searches 
            to refine your identification.
        """

        # 2. File and Technical Evidence
        # Restore compact hints from heuristics and guessit
        likely_show = next(
            (
                v
                for v in [
                    meta.heuristics.get("show"),
                    meta.guessit.get("show"),
                    meta.ai_guess.get("show"),
                ]
                if v
            ),
            None,
        )
        likely_season = next(
            (
                v
                for v in [
                    meta.heuristics.get("season"),
                    meta.guessit.get("season"),
                    meta.ai_guess.get("season"),
                ]
                if v
            ),
            None,
        )

        likely_metadata = {
            "likely_show": likely_show,
            "likely_season": likely_season,
            "duration_sec": meta.technical.duration if meta.technical else None,
            "full_path": str(meta.path),
        }

        # Enrich with disc-level estimates when available
        disc = (meta.heuristics or {}).get("disc_analysis")
        if disc:
            likely_metadata["is_makemkv_rip"] = True
            likely_metadata["dvd_number"] = disc.get("dvd_number")
            likely_metadata["total_discs_in_season"] = disc.get("total_discs_found")
            likely_metadata["file_role"] = (
                "main_episode" if disc.get("is_episode") else "bonus_or_special"
            )
            if disc.get("estimated_episode_number") is not None:
                likely_metadata["estimated_episode"] = disc["estimated_episode_number"]
                likely_metadata["estimated_episode_range_this_disc"] = disc.get(
                    "estimated_episode_range"
                )
                likely_metadata["episode_offset_confidence"] = (
                    "high (all prior discs found)"
                    if disc.get("offset_is_exact")
                    else "medium (some prior discs missing)"
                )

        evidence_file = f"""
            ## EVIDENCE: FILE SYSTEM & TECHNICAL
            {json.dumps(likely_metadata, indent=2)}
        """

        # 3. Content-based Evidence (Subtitles & Cast)
        # Summary and cast profiles are high-confidence signals extracted from the video content itself.
        summary_content = (
            meta.summary.get("summary", "No summary available.")
            if isinstance(meta.summary, dict)
            else str(meta.summary)
        )

        evidence_content = f"""
            ## EVIDENCE: CONTENT ANALYSIS
            ### SUBTITLE SUMMARY
            {summary_content}

            ### CAST PROFILE
            {json.dumps(meta.cast_profile.to_dict() if hasattr(meta.cast_profile, "to_dict") else meta.cast_profile, indent=2)}
        """

        # 4. Disc analysis narrative block (MakeMKV rips only)
        disc_section = ""
        if disc:
            ep_letter = disc.get("episode_letter", "?")
            this_letter = disc.get("this_letter", "?")
            is_ep = disc.get("is_episode", False)
            disc_pos = disc.get("disc_position")
            disc_ep_count = disc.get("disc_episode_count", 0)
            disc_bonus_count = disc.get("disc_bonus_count", 0)
            dvd_num = disc.get("dvd_number", "?")
            total_discs = disc.get("total_discs_found", "?")
            ep_num = disc.get("estimated_episode_number")
            ep_range = disc.get("estimated_episode_range", [])
            prior_dvds = disc.get("prior_dvds_analyzed", [])
            offset = disc.get("episode_offset", 0)
            offset_exact = disc.get("offset_is_exact", False)

            role_line = (
                f"MAIN EPISODE — position {disc_pos} of {disc_ep_count} "
                f"(letter group '{this_letter}' = episode group '{ep_letter}')"
                if is_ep
                else f"BONUS / SPECIAL — letter group '{this_letter}' "
                f"(episode group is '{ep_letter}', bonus groups: "
                f"{disc.get('bonus_letters')})"
            )

            offset_note = (
                f"exact (discs {prior_dvds} counted)"
                if offset_exact
                else f"estimated (only discs {prior_dvds} found of {list(range(1, dvd_num if isinstance(dvd_num, int) else 1))})"
            )

            ep_estimate_block = ""
            if is_ep and ep_num is not None:
                ep_estimate_block = (
                    f"\n            ESTIMATED SEASON EPISODE : {ep_num} ({offset_note})"
                    f"\n            EPISODE RANGE ON THIS DISC: {ep_range}"
                    f"\n            → Primary search target: {likely_show or '?'} "
                    f"S{likely_season or '?'}E{ep_num}"
                )
            elif not is_ep:
                ep_estimate_block = (
                    "\n            → This is a BONUS file. "
                    "Search under Season 0 (Specials) first."
                )

            disc_section = f"""
            ## EVIDENCE: DVD DISC ANALYSIS (MakeMKV rip)
            DISC         : {dvd_num} of ~{total_discs} discs (Season {disc.get('folder_season', likely_season)})
            FILE ROLE    : {role_line}
            DISC CONTENTS: {disc_ep_count} main episode(s), {disc_bonus_count} bonus item(s)
            EPISODE OFFSET FROM PRIOR DISCS: {offset}{ep_estimate_block}
            """

        # 5. Search Commands
        commands = """
            ## AVAILABLE SEARCH COMMANDS
            To gather more information, return a JSON object with status "SEARCHING".
            
            1. **SEARCH_EPISODES**: Fetch episode lists and overviews for a show. 
               - Use "season: 0" for Specials/Movies/OVA.
               - Example: {"type": "SEARCH_EPISODES", "show": "Doctor Who", "season": 0}

            2. **SEARCH_PERSON**: Look up actor/crew credits. 
               - Use names from the Cast Profile to disambiguate similar titles.
               - Example: {"type": "SEARCH_PERSON", "name": "Bryan Cranston"}
        """

        tips_and_tricks = f"""
            ## TIPS AND TRICKS
            - If show is "Doctor Who", query "Christmas Specials" and {likely_season} seasons.
            - If the file name is similar to B1_t00.mkv it means the video was extracted by MakeMKV from a DVD. The episode name is unknown — rely on disc analysis above and subtitle/cast evidence.
            - For MakeMKV bonus files (is_bonus=True), check Season 0 / Specials on TMDB.
        """

        # 6. Output Format
        output_format = """
            ## OUTPUT FORMAT
            - Return ONLY valid JSON.
            - If found: { "status": "FOUND", "reasoning": "...", "show": "...", "season": X, "episode": Y, "title": "...", "confidence_score": 0-100 }
            - If searching: { "status": "SEARCHING", "reasoning": "...", "queries": [...] }
        """

        # 7. History
        # If iterations exceed a certain threshold, we prune older history to save tokens.
        # Keeping only the most recent 2 searches provides context without context-window bloat.
        pruned_history = (
            search_history[-2:] if len(search_history) > 2 else search_history
        )
        history_section = f"""
            ## PREVIOUS SEARCH RESULTS
            {json.dumps(pruned_history, indent=2) if pruned_history else "No searches performed yet."}
        """

        # Assemble final prompt and apply cleandoc ONCE at the end
        full_sections = [
            identity,
            evidence_file,
            evidence_content,
        ]
        if disc_section:
            full_sections.append(disc_section)
        full_sections += [
            commands,
            tips_and_tricks,
            output_format,
            history_section,
        ]
        prompt = inspect.cleandoc("\n\n".join(full_sections))
        return prompt
