import json
import inspect
import re
import math
from typing import List, Dict, Any, Optional
from mediatamer.signals.tmdb import fetch_tmdb_episodes, fetch_tmdb_person_credits
from mediatamer.signals.tvdb import fetch_tvdb_info
from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata
from mediatamer.signals.technical import TechnicalSignals
from mediatamer.signals.scoring import score_episode_match


def _as_technical(technical) -> TechnicalSignals:
    """Return a TechnicalSignals object whether technical is already one or a dict."""
    if isinstance(technical, TechnicalSignals):
        return technical
    return TechnicalSignals.from_dict(technical or {})


def match_episode(meta: VideoMetadata, config: dict) -> None:
    matcher = AIVideoMatcher()
    matcher.match(meta, config)


class AIVideoMatcher:
    def match(self, meta: VideoMetadata, config: dict) -> None:
        self.config = config
        self.tmdb_api_key = self.config.get("tmdb-api-key")
        self.tvdb_api_key = self.config.get("tvdb-api-key")

        print(f"[AI Episode Matcher] Analyzing iteratively: {meta.path.name}")
        sub_text = meta.subtitles or ""

        # ── Step 0: deterministic pre-filter from OVDB cast cross-reference ──
        # Episodes with match_count >= 2 have at least two OCR-extracted people
        # confirmed in TMDB credits. Score them heuristically; if a clear winner
        # exists, skip the expensive LLM loop entirely.
        meta.ai_match = self._try_ovdb_candidates(meta, sub_text)

        # # ── Step 1: LLM iterative agentic loop (fallback) ────────────────────
        # search_history = []
        # max_iterations = 8
        # iteration = 0

        # while iteration < max_iterations:
        #     iteration += 1
        #     print(f"\n[AI Agent Loop] Iteration {iteration}/{max_iterations}.")
        #     prompt = self._build_agentic_prompt(meta, search_history)
        #     response = run_ai(prompt, config, json_mode=True)

        #     try:
        #         action = json.loads(response)
        #     except Exception as e:
        #         print(f"[AI Agent Loop] JSON Parsing Error: {e}")
        #         meta.ai_match = {"error": f"Failed to parse LLM response: {e}"}
        #         break

        #     status = action.get("status")
        #     reasoning = action.get("reasoning", "No reasoning provided.")
        #     print(f"  -> AI Status: {status}")
        #     print(f"  -> AI Reasoning: {reasoning}")

        #     if status == "FOUND":
        #         show = action.get("show")
        #         season = action.get("season")
        #         episode_num = action.get("episode")
        #         title = action.get("title")
        #         video_type = action.get("type")

        #         # Verify with scoring to be safe
        #         print(
        #             f"  -> Trying to verify AI's final answer: {show} S{season}E{episode_num}"
        #         )
        #         _, season_episodes = fetch_tmdb_episodes(
        #             show, season, self.tmdb_api_key
        #         )
        #         target_ep = next(
        #             (
        #                 ep
        #                 for ep in season_episodes
        #                 if ep.get("episode_number") == episode_num
        #             ),
        #             None,
        #         )

        #         if target_ep:
        #             score_res = score_episode_match(
        #                 target_ep,
        #                 meta.path,
        #                 _as_technical(meta.technical),
        #                 sub_text=sub_text,
        #                 context_hints={
        #                     "is_likely_episode": (meta.guessit or {})
        #                     .get("heuristics", {})
        #                     .get("is_episode"),
        #                     "season_number": season,
        #                 },
        #             )
        #             final_score = score_res["score"]
        #             print(f"  -> Verification Score: {final_score}")

        #             meta.ai_match = {
        #                 "show": show,
        #                 "season": season,
        #                 "episode": episode_num,
        #                 "title": title or target_ep.get("name"),
        #                 "best_candidate": target_ep,
        #                 "score": final_score,
        #                 "reasoning": reasoning + f" (Verified Score: {final_score})",
        #                 "ai_full_response": action,
        #                 "type": video_type,
        #                 "phase": f"agent_found_iter_{iteration}",
        #             }
        #         else:
        #             print(
        #                 "  -> Could not locate the episode in TMDB to verify. Accepting blind AI response."
        #             )
        #             meta.ai_match = {
        #                 "show": show,
        #                 "season": season,
        #                 "episode": episode_num,
        #                 "title": title,
        #                 "score": action.get("confidence_score", 0.0),
        #                 "reasoning": reasoning,
        #                 "ai_full_response": action,
        #                 "phase": f"agent_found_unverified_iter_{iteration}",
        #             }
        #         meta.ai_match["best_match"] = {
        #             "show_name": show,
        #             "season": season,
        #             "episode": episode_num,
        #             "title": meta.ai_match.get("title", ""),
        #         }
        #         break

        #     elif status == "SEARCHING":
        #         queries = action.get("queries", [])
        #         if not queries:
        #             print(
        #                 "  -> AI returned SEARCHING but provided no queries. Stopping."
        #             )
        #             break

        #         print(f"  -> Queries: {queries}")
        #         print(f"  -> Executing {len(queries)} queries...")
        #         target_dur = meta.technical["duration"] if meta.technical else None
        #         history_entry = self._execute_search_queries(queries, target_dur)
        #         search_history.extend(history_entry)

        #     else:
        #         print(f"  -> Unknown status '{status}'. Stopping.")
        #         break
        # else:
        #     print("[AI Agent Loop] Max iterations reached without finding a match.")
        #     meta.ai_match = {
        #         "error": "Max iterations reached without finding an episode."
        #     }

    def _try_ovdb_candidates(
        self,
        meta: VideoMetadata,
        sub_text: str,
    ) -> Optional[Dict[str, Any]]:
        """Identify the episode from OVDB cast-ranked candidates.

        Strategy:
          1. Keep only candidates with match_count >= 2 (at least two OCR-confirmed
             cast members).
          2. If one episode has strictly more matches than all others, pick it
             immediately (no LLM call needed).
          3. Otherwise ask the LLM to pick the best match by comparing each
             candidate's official overview against the subtitle-derived summary.
             This is a single, cheap, focused LLM call — not an iterative search
             loop.
        Returns a result dict on success, or None to fall through to the full LLM
        loop.
        """
        candidates = (meta.ovdb or {}).get("ranked_episodes", [])

        # Use a single LLM call to compare overviews vs summary.
        subtitle_summary = (
            (meta.summary or {}).get("summary", "").strip()
            if isinstance(meta.summary, dict)
            else str(meta.summary or "").strip()
        )
        if not subtitle_summary:
            print(
                f"[OVDB pre-filter] {len(candidates)} candidate(s) with match_count >= 2,"
                " but no subtitle summary available. Falling through to LLM loop."
            )
            return None

        print(
            f"[OVDB pre-filter] {len(candidates)} candidate(s) with match_count >= 2."
            " Using summary comparison to disambiguate."
        )
        best_ep = self._pick_by_summary_llm(candidates, subtitle_summary)
        if best_ep is None:
            return None
        people_str = ", ".join(
            p.get("person_name", "") for p in best_ep.get("matched_people", [])
        )
        return self._build_result(
            best_ep,
            f"Summary comparison among {len(candidates)} cast-ranked candidates ({people_str})",
            "ovdb_cast_prefilter_summary",
        )

    # ------------------------------------------------------------------
    # Deterministic summary-vs-overview scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase, strip punctuation, remove English/French stop words."""
        _STOPWORDS = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "his",
            "her",
            "their",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "has",
            "have",
            "had",
            "he",
            "she",
            "they",
            "it",
            "who",
            "that",
            "this",
            "as",
            "by",
            "from",
            "not",
            "no",
            "can",
            "will",
            "just",
            "do",
            "does",
            "its",
            "into",
            "when",
            # French
            "le",
            "la",
            "les",
            "un",
            "une",
            "des",
            "du",
            "de",
            "et",
            "en",
            "est",
            "il",
            "elle",
            "ils",
            "elles",
            "se",
            "sa",
            "son",
            "ses",
            "que",
            "qui",
            "ne",
            "pas",
            "sur",
            "au",
            "aux",
            "par",
            "si",
        }
        words = re.findall(r"[a-záàâéèêëïîôùûüç]+", text.lower())
        return [w for w in words if w not in _STOPWORDS and len(w) > 2]

    @staticmethod
    def _idf_scores(candidate_tokens: List[List[str]]) -> Dict[str, float]:
        """Compute IDF for each word across all candidates.
        Rare words (appear in few overviews) score higher.
        """
        N = len(candidate_tokens)
        df: Dict[str, int] = {}
        for tokens in candidate_tokens:
            for w in set(tokens):
                df[w] = df.get(w, 0) + 1
        return {w: math.log((N + 1) / (count + 1)) for w, count in df.items()}

    def _score_overlap(
        self,
        summary_tokens: List[str],
        overview_tokens: List[str],
        idf: Dict[str, float],
    ) -> float:
        """Sum IDF weights of summary words that appear in the overview."""
        overview_set = set(overview_tokens)
        return sum(idf.get(w, 0.0) for w in summary_tokens if w in overview_set)

    def _pick_by_summary(
        self,
        candidates: List[Dict[str, Any]],
        subtitle_summary: str,
    ) -> Optional[Dict[str, Any]]:
        """Identify which candidate's overview best matches the subtitle summary
        using deterministic TF-IDF keyword overlap.  Falls back to the LLM only
        when the top two candidates are within 15% of each other.
        """
        # Tokenize
        summary_tokens = self._tokenize(subtitle_summary)
        overviews = [ep.get("overview", "") for ep in candidates]
        overview_token_lists = [self._tokenize(ov) for ov in overviews]

        # IDF is computed over candidate overviews only (not the summary) so that
        # words appearing in every episode ("Doctor", "Clara") get down-weighted.
        idf = self._idf_scores(overview_token_lists)

        scores = [
            self._score_overlap(summary_tokens, ov_tokens, idf)
            for ov_tokens in overview_token_lists
        ]

        for i, (ep, sc) in enumerate(zip(candidates, scores)):
            print(
                f"[OVDB overlap] S{ep['season']:02d}E{ep['episode']:02d}"
                f" '{ep['title']}' overlap_score={sc:.3f}"
            )

        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_score = scores[best_idx]

        # Check runner-up: if it's within 15% of the best, we're not confident.
        sorted_scores = sorted(scores, reverse=True)
        second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        margin = (best_score - second_score) / (best_score + 1e-9)

        print(
            f"[OVDB overlap] Best: S{candidates[best_idx]['season']:02d}"
            f"E{candidates[best_idx]['episode']:02d}"
            f" '{candidates[best_idx]['title']}'"
            f" score={best_score:.3f}, margin={margin:.1%}"
        )

        if best_score > 0 and margin >= 0.15:
            return candidates[best_idx]

        # Scores too close — fall back to LLM.
        print("[OVDB overlap] Scores too close, falling back to LLM comparison.")
        return self._pick_by_summary_llm(candidates, subtitle_summary)

    def _pick_by_summary_llm(
        self,
        candidates: List[Dict[str, Any]],
        subtitle_summary: str,
    ) -> Optional[Dict[str, Any]]:
        """LLM fallback: ask the model to compare overviews against the summary.
        Used only when keyword overlap cannot disambiguate."""

        # Build a compact numbered list of candidates for the prompt.
        candidate_list = "\n".join(
            f"{i + 1}. S{ep['season']:02d}E{ep['episode']:02d} '{ep['title']}': "
            f"{ep.get('overview', 'No overview available.')}"
            for i, ep in enumerate(candidates)
        )

        prompt = inspect.cleandoc(f"""
            You are a TV episode identification assistant. You must identify which episode a video file
            corresponds to by carefully comparing a summary extracted from its subtitles against a list
            of official episode overviews.

            IMPORTANT: The subtitle summary may be in any language (e.g. French, Spanish,
            German). Translate it mentally to compare with the English overviews.

            ## SUBTITLE SUMMARY
            {subtitle_summary}

            ## CANDIDATES
            {candidate_list}

            ## INSTRUCTIONS
            1. Read the subtitle summary carefully and extract the key plot elements:
               - Where does the story take place? (underwater base, Arctic, space station, London…)
               - What is the main threat or conflict? (ghosts, Daleks, Zygons, warlord…)
               - What are the main characters doing?
               - Are any supporting character names (not the Doctor / companion) mentioned?
            2. For EACH candidate, check whether its overview aligns with those plot elements.
               - Unique LOCATIONS and specific THREATS are strong evidence of a match.
               - Do NOT use "the Doctor" or companion names alone — they appear in every episode.
               - For two-parters sharing the same location/threat, prefer part 1 if the summary
                 describes a discovery/introduction, part 2 if it describes a resolution/escape.
            3. Pick the ONE candidate whose overview best fits the subtitle summary.
            4. If truly no candidate fits, return index 0.

            ## OUTPUT
            Return ONLY valid JSON with exactly these keys:
            - "plot_elements": short list of the key plot elements you extracted from the subtitle summary
            - "index": the 1-based number of the best matching candidate (integer, 0 if no match)
            - "reasoning": one sentence explaining why this candidate matches better than the others
            - "confidence": integer 0-100 (use 60-80 when a unique location or threat clearly
              matches; 80+ for multiple specific details; below 40 only when genuinely uncertain)
        """)

        print("[OVDB pre-filter] --- SUBTITLE SUMMARY ---")
        print(subtitle_summary)
        print("[OVDB pre-filter] --- CANDIDATE OVERVIEWS ---")
        print(candidate_list)
        print("[OVDB pre-filter] --- END ---")
        print(
            "[OVDB pre-filter] (LLM fallback) Sending summary-comparison prompt to LLM..."
        )
        response = run_ai(prompt, self.config, json_mode=True)
        try:
            result = json.loads(response)
        except Exception as e:
            print(f"[OVDB pre-filter] Failed to parse LLM response: {e}")
            return None

        idx = result.get("index", 0)
        confidence = result.get("confidence", 0)
        reasoning = result.get("reasoning", "")
        plot_elements = result.get("plot_elements", [])
        print(f"[OVDB pre-filter] LLM extracted plot elements: {plot_elements}")
        print(
            f"[OVDB pre-filter] LLM chose index={idx}, confidence={confidence}: {reasoning}"
        )

        if idx == 0 or confidence < 40:
            print(
                "[OVDB pre-filter] LLM not confident enough. Falling through to LLM loop."
            )
            return None

        if not (1 <= idx <= len(candidates)):
            print(f"[OVDB pre-filter] LLM returned out-of-range index {idx}. Ignoring.")
            return None

        return candidates[idx - 1]

    @staticmethod
    def _build_result(ep: Dict[str, Any], reasoning: str, phase: str) -> Dict[str, Any]:
        """Build a standardised ai_match result dict from an OVDB episode entry."""
        best_match = {
            "show_name": ep.get("show_name", ""),
            "season": ep.get("season"),
            "episode": ep.get("episode"),
            "title": ep.get("title", ""),
        }
        return {
            "best_match": best_match,
            "show": ep.get("show_name", ""),
            "season": ep.get("season"),
            "episode": ep.get("episode"),
            "title": ep.get("title", ""),
            "score": None,
            "match_count": ep.get("match_count"),
            "matched_people": ep.get("matched_people", []),
            "best_candidate": ep,
            "reasoning": reasoning,
            "phase": phase,
        }

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
            print(f"Warning] Unknown season alias '{season}', defaulting to Season 0")
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
                print(f"Fetching TMDB for Person '{name}'")
                credits = fetch_tmdb_person_credits(name, self.tmdb_api_key)

                # # Keep top 15 to avoid huge context, truncate overviews
                # filtered_credits = []
                # for cr in credits[:15]:
                #     ov = cr.get("overview", "")
                #     print(f"Overview for credit '{name}': {ov}")
                #     cr["overview"] = (ov[:200] + "...") if len(ov) > 200 else ov
                #     filtered_credits.append(cr)

                print(f"Found {len(credits)} credits for '{name}'")
                results.append(
                    {
                        "query": {"type": "SEARCH_PERSON", "name": name},
                        "results_count": len(credits),
                        "credits": credits,
                    }
                )
            else:
                sh = q.get("show")
                se_raw = q.get("season")
                if not sh or se_raw is None:
                    continue
                se = self._resolve_season(se_raw)

                print(f"Fetching TMDB & TVDB for '{sh}' Season {se} (raw: '{se_raw}')")
                # Fetch TMDB
                _, tmdb_eps = fetch_tmdb_episodes(sh, se, self.tmdb_api_key)
                # Fetch TVDB
                resolved_name, tvdb_eps = fetch_tvdb_info(sh, se, self.tvdb_api_key)

                # Combine distinct episodes, truncate overviews
                # Key includes show name to keep classic vs revival episodes separate
                combined_hash = {}
                for ep in tmdb_eps + tvdb_eps:
                    ep_id = ep.get("episode_number")
                    ep_show = ep.get("_show_name") or resolved_name
                    hash_key = (ep_show, ep_id)
                    if ep_id and hash_key not in combined_hash:
                        ov = ep.get("overview") or ""
                        combined_hash[hash_key] = {
                            "show name": ep_show,
                            "season_number": se,
                            "episode_number": ep_id,
                            "name": ep.get("name"),
                            "overview": ov,
                            "runtime_min": ep.get("runtime"),
                            "guest_stars": [
                                g.get("name") for g in ep.get("guest_stars", [])
                            ],
                        }

                all_eps = list(combined_hash.values())

                # Duration filter (tolerance: +/- 15 mins) — only apply if it leaves at least one result
                if target_duration_sec:
                    duration_filtered = [
                        ep
                        for ep in all_eps
                        if not ep["runtime_min"]
                        or abs((ep["runtime_min"] * 60) - target_duration_sec) <= 900
                    ]
                    filtered_eps = duration_filtered if duration_filtered else all_eps
                else:
                    filtered_eps = all_eps

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
        # Single consolidated context built by guessit.build_best_context().
        # Each field carries a _source key so the AI knows its confidence.
        ctx = (meta.guessit or {}).get("context") or {}

        # Convenience aliases still used by other parts of the prompt builder
        likely_show = ctx.get("show") or None
        if likely_show == "unknown":
            likely_show = None
        likely_season = ctx.get("season") or None
        if likely_season == "unknown":
            likely_season = None

        likely_metadata = {
            "duration_sec": meta.technical["duration"] if meta.technical else None,
            "full_path": str(meta.path),
            **ctx,
        }

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
credits_names = {meta.cast_profile.get("credits_names", meta.cast_profile.get("real_actors", []) + meta.cast_profile.get("crew_names", []))}
fictional_characters = {meta.cast_profile["fictional_characters"]}
        """

        # 4. Search Commands
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
- If show is "Doctor Who", also query Season 0 (Christmas Specials) alongside season {likely_season}.
- Fields with source "unknown" in EVIDENCE mean the agent must search broadly.
- Fields with source "disc_analysis_high" are reliable — use them as primary search targets.
- Fields with source "disc_analysis_medium" are estimates — verify against episode durations.
- For file_role "bonus_or_special", start with Season 0 / Specials on TMDB.
"""

        # 5. Output Format
        output_format = """
## OUTPUT FORMAT
- Return ONLY valid JSON.
- If found: { "status": "FOUND", "reasoning": "...", "show": "...", "season": X, "episode": Y, "title": "...", "confidence_score": 0-100 }
- If searching: { "status": "SEARCHING", "reasoning": "...", "queries": [...] }
        """

        # 6. History
        # Keeping only the most recent 2 searches to limit context size.
        pruned_history = (
            search_history[-2:] if len(search_history) > 2 else search_history
        )
        history_section = f"""
## PREVIOUS SEARCH RESULTS
{json.dumps(pruned_history, indent=2) if pruned_history else "No searches performed yet."}
        """

        full_sections = [
            identity,
            evidence_file,
            evidence_content,
            commands,
            tips_and_tricks,
            output_format,
            history_section,
        ]
        prompt = inspect.cleandoc("\n\n".join(full_sections))
        print("[ai_video_matcher] Prompt sent to AI:\n", prompt)
        return prompt
