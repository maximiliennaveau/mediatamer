import json
import inspect
import re
import math
from typing import List, Dict, Any, Optional
from mediatamer.ai import run_ai
from mediatamer.signals.video_metadata import VideoMetadata


def match_episode(meta: VideoMetadata, config: dict) -> None:
    matcher = AIVideoMatcher()
    matcher.match(meta, config)


class AIVideoMatcher:
    def match(self, meta: VideoMetadata, config: dict) -> None:
        self.config = config
        self.tmdb_api_key = self.config.get("tmdb-api-key")
        self.tvdb_api_key = self.config.get("tvdb-api-key")

        print(f"[AI Episode Matcher] Analyzing: {meta.path.name}")
        sub_text = meta.subtitles or ""
        meta.ai_match = self._try_ovdb_candidates(meta, sub_text)

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
