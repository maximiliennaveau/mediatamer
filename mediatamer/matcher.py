from typing import List, Dict, Any, Optional
import re
from pathlib import Path
import requests

from mediatamer.signals.filename import parse_filename
from mediatamer.extract_subtitle import extract_subtitle_text, extract_credits_text
from mediatamer.utils import detect_language
from mediatamer.signals.tmdb import fetch_tmdb_episodes, lang_to_tmdb_locale
from mediatamer.signals.context import infer_context_from_path
from mediatamer.signals.scoring import score_episode_match, parse_disc_track
from mediatamer.signals.unified import MediaSignals



class EpisodeMatcher:
    def __init__(self, file_path: Path, tmdb_api_key: str, show_name: Optional[str] = None, season_number: Optional[int] = None):
        self.file_path = file_path
        self.tmdb_api_key = tmdb_api_key
        self.tmdb_episodes = []
        self.signals = MediaSignals.from_path(file_path)
        
        # Result Attributes
        self.show_name = show_name
        self.season_number = season_number
        self.episode_number = None
        self.best_candidate = None
        self.candidates = []
        
        # Hints
        self.is_likely_episode = None # Set by caller (bool)
        self.last_episode_matched = None # Set by caller (int)
        self.has_global_indices = False # Set by caller (bool)

    def find_metadata(self) -> None:
        """
        Orchestrate the metadata finding process:
        1. Infer Show/Season from path (if not provided).
        2. Detect subtitle language.
        3. Fetch potential episodes from TMDB in detected language.
        4. Match file against episodes (text + disc structure).
        5. Set attributes based on best match.
        """
        if not self.show_name or self.season_number is None:
            self._infer_context()
            
        if self.show_name:
            # Detect language and extract credits using optimized ranges
            sub_text = extract_subtitle_text(self.file_path, prefer_non_pgs=True, duration_limit=600.0)
            credits_text = extract_credits_text(self.file_path, custom_ranges=self.signals.suggested_ocr_ranges)
            # Cache so _match_file can reuse without re-extracting
            self._sub_text_cache = sub_text
            self._credits_text_cache = credits_text
            sample = (credits_text or '') + '\n' + (sub_text or '')
            self._detected_lang = detect_language(sample)
            self._tmdb_locale = lang_to_tmdb_locale(self._detected_lang)
            if self._detected_lang and self._detected_lang != 'en':
                print(f"  [LANG] Detected subtitle language: {self._detected_lang} → fetching TMDB in {self._tmdb_locale}")
            self._fetch_tmdb_episodes()

        if self.tmdb_episodes:
            self.candidates = self._match_file()
            if self.candidates:
                best = self.candidates[0]
                if best['score'] >= 40:
                    self.best_candidate = best
                    self.episode_number = best['episode'].get('episode_number')
    
    def _infer_context(self):
        """Infer Show Name and Season from directory structure."""
        show_name, season_number = infer_context_from_path(self.file_path)
        
        if show_name:
            self.show_name = show_name
            self.season_number = season_number
        else:
            self.season_number = None
            self.show_name = None
            print(f"Could not infer show name and season from {self.file_path.parent.name}.")
            
    def _fetch_tmdb_episodes(self):
        """Fetch episodes from TMDB for the identified show and season.

        Delegates to signals.tmdb.fetch_tmdb_episodes.
        """
        if not self.show_name or not self.season_number:
            return

        locale = getattr(self, '_tmdb_locale', 'en-US')
        
        normalized_name, episodes = fetch_tmdb_episodes(
            self.show_name, 
            self.season_number, 
            self.tmdb_api_key, 
            locale
        )
        
        self.show_name = normalized_name
        self.tmdb_episodes = episodes

    def _match_file(self) -> List[Dict[str, Any]]:
        """Run scoring logic against downloaded episodes."""
        if not self.file_path.exists():
            return []

        # 1. Gather Signals
        sub_text = getattr(self, '_sub_text_cache', None)
        credits_text = getattr(self, '_credits_text_cache', None)
        
        context_hints = {
            'is_likely_episode': self.is_likely_episode,
            'last_episode_matched': self.last_episode_matched,
            'has_global_indices': self.has_global_indices,
            'season_number': self.season_number
        }

        # 2. Score
        candidates = []
        for ep in self.tmdb_episodes:
            res = score_episode_match(
                ep, 
                self.file_path, 
                self.signals, 
                sub_text=sub_text, 
                credits_text=credits_text, 
                context_hints=context_hints
            )
            candidates.append({
                'episode': ep,
                'score': res['score'],
                'reasons': res['reasons']
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates
