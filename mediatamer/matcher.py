from typing import List, Dict, Any, Optional
import re
from pathlib import Path

from mediatamer.signals.filename import parse_filename
from mediatamer.signals.technical import get_technical_metadata
from mediatamer.extract_subtitle import extract_subtitle_text, extract_pgs_as_text
from mediatamer.signals.subtitle_hash import compute_file_hash, lookup_subtitle_hash

class EpisodeMatcher:
    def __init__(self, tmdb_episodes: List[Dict[str, Any]]):
        self.tmdb_episodes = tmdb_episodes
        # Index episodes by ID and Episode Number for quick lookup
        self.ep_by_id = {ep['id']: ep for ep in tmdb_episodes}
        self.ep_by_num = {ep.get('episode_number'): ep for ep in tmdb_episodes}

    def match_file(self, file_path: Path, language='fr-FR') -> List[Dict[str, Any]]:
        """
        Compare a video file against the episodes list and return scored candidates.
        Returns a list of dicts: {'episode': ep_data, 'score': float, 'reasons': list}
        """
        if not file_path.exists():
            return []

        # 1. Gather Signals
        signals = {}
        
        # Technical (Duration)
        tech = get_technical_metadata(file_path)
        duration = tech.get('duration')
        signals['duration'] = duration

        # Filename
        fname_meta = parse_filename(file_path)
        signals['filename'] = fname_meta

        # Subtitle Text (Try SRT first, then PGS/OCR)
        sub_text = extract_subtitle_text(file_path, prefer_non_pgs=True)
        if not sub_text:
            # Fallback to OCR
            print(f"No text subtitles found for {file_path.name}, attempting OCR...")
            sub_text = extract_pgs_as_text(file_path)
        signals['subtitle_text'] = sub_text

        # 2. Score against all episodes
        candidates = []
        
        for ep in self.tmdb_episodes:
            score = 0.0
            reasons = []

            # -- Hash Match (Theoretically 100% if we had DB) --
            # (Skipped for now as we have no DB)

            # -- Duration Match --
            ep_runtime = ep.get('runtime') # in minutes
            if duration and ep_runtime:
                ep_duration_sec = ep_runtime * 60
                diff = abs(duration - ep_duration_sec)
                
                # If within 45 seconds, give good score
                if diff < 45:
                    score += 50.0
                    reasons.append(f"Duration match ({diff:.0f}s diff)")
                elif diff < 120:
                    score += 20.0
                elif diff > 600: # > 10 mins off
                    score -= 50.0 # Penalty for massive mismatch

            # -- Filename Match --
            # If filename has explicit SxxExx and it matches this episode
            if fname_meta['season'] and fname_meta['episode']:
                 # Check if season matches (if we know the season context) 
                 # We assume the caller filtered tmdb_episodes for the correct season, 
                 # or we check if the episode's season_number matches.
                 if int(ep.get('season_number', 0)) == int(fname_meta['season']):
                     if int(ep.get('episode_number', -1)) == int(fname_meta['episode']):
                         score += 80.0
                         reasons.append("Filename SxxExx match")

            # -- Text Content Match --
            if sub_text and ep.get('name'):
                ep_title = ep['name'].lower()
                st_lower = sub_text.lower()
                
                # Check for exact title in text
                if ep_title in st_lower:
                    score += 100.0
                    reasons.append(f"Title '{ep_title}' found in subtitles")
                else:
                    # Token overlap
                    # Remove common words?
                    # valid words: 
                    tokens = [w for w in re.findall(r"\w+", ep_title) if len(w) > 3]
                    if tokens:
                        found_count = 0
                        for t in tokens:
                            if t in st_lower:
                                found_count += 1
                        
                        if found_count > 0:
                            ratio = found_count / len(tokens)
                            pts = ratio * 60.0
                            score += pts
                            reasons.append(f"Title words overlap {ratio:.2f}")

            # Normalize/Finalize
            candidates.append({
                'episode': ep,
                'score': score,
                'reasons': reasons
            })

        # Sort by score descending
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates
