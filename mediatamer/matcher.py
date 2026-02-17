from typing import List, Dict, Any, Optional
import re
from pathlib import Path
import requests

from mediatamer.signals.filename import parse_filename
from mediatamer.signals.technical import get_technical_metadata
from mediatamer.extract_subtitle import extract_subtitle_text, extract_credits_text

class EpisodeMatcher:
    def __init__(self, file_path: Path, tmdb_api_key: str):
        self.file_path = file_path
        self.tmdb_api_key = tmdb_api_key
        self.tmdb_episodes = []
        
        # Result Attributes
        self.show_name = None
        self.season_number = None
        self.episode_number = None
        self.best_candidate = None
        self.candidates = []

    def find_metadata(self) -> None:
        """
        Orchestrate the metadata finding process:
        1. Infer Show/Season from path.
        2. Fetch potential episodes from TMDB.
        3. Match file against episodes.
        4. Set attributes based on best match.
        """
        self._infer_context()
        if self.show_name:
            self._fetch_tmdb_episodes()
            
        if self.tmdb_episodes:
            self.candidates = self._match_file()
            if self.candidates:
                # Naive best match for now, can be improved with thresholds
                best = self.candidates[0]
                if best['score'] >= 40: # Lowered threshold
                    self.best_candidate = best
                    self.episode_number = best['episode'].get('episode_number')
                    # If we found a match, trust its season/show data if we were unsure?
                    # For now, trust our initial context for show/season unless mismatch
    
    def _infer_context(self):
        """Infer Show Name and Season from directory structure."""
        # Simple heuristic: parent folder name
        # "Doctor_Who_S9_DVD3" -> Show: Doctor Who, Season: 9
        parent_dir = self.file_path.parent.name
        
        m = re.search(r'(.+?)_?[sS](\d+)(?:_?[dD][vV][dD](\d+))?', parent_dir, re.I)
        if m:
            raw_show = m.group(1).replace('_', ' ')
            self.season_number = int(m.group(2))
            
            # Special case normalization
            if raw_show.lower() in ('dr who', 'doctor who'):
                self.show_name = 'Doctor Who'
            else:
                self.show_name = raw_show.title()

            # Extras detection (heuristic: files starting with C)
            if self.file_path.name.startswith('C'):
                self.show_name += " - Extras"
        else:
            # Fallback patterns
            self.season_number = None
            self.show_name = None
            print(f"Could not infer show name and season from {parent_dir}.")
            
    def _fetch_tmdb_episodes(self):
        """Fetch episodes from TMDB for the identified show and season."""
        if not self.show_name or not self.season_number:
            return

        try:
            # 1. Search for Show ID
            search_query = self.show_name
            is_extras = " - Extras" in search_query
            if is_extras:
                search_query = search_query.replace(" - Extras", "")

            search_url = f"https://api.themoviedb.org/3/search/tv"
            params = {'api_key': self.tmdb_api_key, 'query': search_query, 'language': 'en-US'}
            resp = requests.get(search_url, params=params, timeout=10)
            if not resp.ok: return
            
            results = resp.json().get('results', [])
            best_show = None
            
            # Try to match the exact show name (with or without extras)
            for s in results:
                if s['name'].lower() == search_query.lower():
                    best_show = s
                    break
            
            # If we were looking for "Doctor Who - Extras" specifically and found "Doctor Who Extra", use it
            if not best_show and is_extras:
                for s in results:
                    if "extra" in s['name'].lower():
                        best_show = s
                        break

            if not best_show and results:
                best_show = results[0]
            
            if not best_show: return
            
            show_id = best_show['id']
            # Correct show name from ID (keep the suffix if it was intentional)
            tmdb_name = best_show['name']
            if is_extras and "extra" not in tmdb_name.lower():
                 self.show_name = f"{tmdb_name} - Extras"
            else:
                 self.show_name = tmdb_name

            # 2. Get Episodes
            # # Doctor Who 2005 Special Handling
            # if tmdb_name == 'Doctor Who' and '2005' in best_show.get('first_air_date', ''):
            #     group_id = '65622094244182012dab7ac1' # Blu-ray Order
            #     group_url = f"https://api.themoviedb.org/3/tv/episode_group/{group_id}"
            #     resp = requests.get(group_url, params={'api_key': self.tmdb_api_key, 'language': 'en-US'})
            #     if resp.ok:
            #         groups = resp.json().get('groups', [])
            #         for g in groups:
            #             # If it's extras, maybe it's in a specific group or season 0
            #             target = f"Season {self.season_number}"
            #             if is_extras:
            #                  # Look for "Specials" or similar in groups?
            #                  if "Special" in g['name']:
            #                      self.tmdb_episodes.extend(g['episodes'])
                        
            #             if target in g['name']:
            #                 self.tmdb_episodes.extend(g['episodes'])
                    
            #         if self.tmdb_episodes:
            #             return

            # Standard Season Lookup
            season_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{self.season_number}"
            resp = requests.get(season_url, params={'api_key': self.tmdb_api_key, 'language': 'en-US', 'append_to_response': 'credits'})
            if resp.ok:
                episodes = resp.json().get('episodes', [])
                # Fetch detailed credits for each episode
                for ep in episodes:
                    ep_num = ep.get('episode_number')
                    if ep_num:
                        # Get episode credits
                        credits_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{self.season_number}/episode/{ep_num}/credits"
                        credits_resp = requests.get(credits_url, params={'api_key': self.tmdb_api_key})
                        if credits_resp.ok:
                            credits_data = credits_resp.json()
                            ep['crew'] = credits_data.get('crew', [])
                            ep['guest_stars'] = credits_data.get('guest_stars', [])
                self.tmdb_episodes.extend(episodes)
            
            # If it's extras, also pull Specials (Season 0)
            if is_extras or not self.tmdb_episodes:
                spec_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/0"
                resp = requests.get(spec_url, params={'api_key': self.tmdb_api_key, 'language': 'en-US'})
                if resp.ok:
                    episodes = resp.json().get('episodes', [])
                    # Fetch detailed credits for specials too
                    for ep in episodes:
                        ep_num = ep.get('episode_number')
                        if ep_num:
                            credits_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/0/episode/{ep_num}/credits"
                            credits_resp = requests.get(credits_url, params={'api_key': self.tmdb_api_key})
                            if credits_resp.ok:
                                credits_data = credits_resp.json()
                                ep['crew'] = credits_data.get('crew', [])
                                ep['guest_stars'] = credits_data.get('guest_stars', [])
                    self.tmdb_episodes.extend(episodes)

        except Exception as e:
            print(f"TMDB Fetch Error: {e}")

    def _match_file(self) -> List[Dict[str, Any]]:
        """Run scoring logic against downloaded episodes."""
        if not self.file_path.exists():
            return []

        # 1. Gather Signals
        signals = {}
        
        # Technical (Duration, Tags)
        tech = get_technical_metadata(self.file_path)
        duration = tech.get('duration')
        tags = tech.get('tags', {})
        embedded_title = tags.get('title')
        
        # Filename
        fname_meta = parse_filename(self.file_path)
        
        # Subtitle Text (Try SRT first, then PGS/OCR)
        sub_text = extract_subtitle_text(self.file_path, prefer_non_pgs=True)
        
        # Credits Text (targeted extraction from opening/closing)
        credits_text = extract_credits_text(self.file_path, opening_duration=180.0, closing_duration=180.0)
        # Note: We rely on extract_subtitle_text's internal fallback to OCR now

        # 2. Score
        candidates = []
        for ep in self.tmdb_episodes:
            score = 0.0
            reasons = []

            # -- Duration Match --
            ep_runtime = ep.get('runtime')
            if duration and ep_runtime:
                ep_duration_sec = ep_runtime * 60
                diff = abs(duration - ep_duration_sec)
                if diff < 45:
                    score += 50.0
                    reasons.append(f"Duration match ({diff:.0f}s diff)")
                elif diff < 120:
                    score += 20.0
                elif diff > 600:
                    # Actually, if we are in main show matching, runtime is very strong.
                    score -= 50.0

            # -- Filename Match --
            if fname_meta['season'] and fname_meta['episode']:
                 if int(ep.get('season_number', 0)) == int(fname_meta['season']):
                     if int(ep.get('episode_number', -1)) == int(fname_meta['episode']):
                         if fname_meta.get('episode_is_explicit', True):
                             score += 80.0
                             reasons.append("Filename SxxExx match (Explicit)")
                         else:
                             score += 20.0 # Lower confidence for tXX patterns
                             reasons.append(f"Filename index '{fname_meta['episode']}' match (Guessed from tXX)")

            # -- Extra Detection --
            if 'extra' in self.file_path.name.lower():
                # If the episode name also contains 'Extra', it's a good match
                if 'extra' in ep.get('name', '').lower():
                    score += 40.0
                    reasons.append("Filename and Episode both contain 'Extra'")

            # -- Embedded Title Match --
            if embedded_title and ep.get('name'):
                et_lower = embedded_title.lower()
                ep_title = ep['name'].lower()
                if ep_title in et_lower:
                    score += 100.0
                    reasons.append(f"Title '{ep_title}' found in MKV header tags")
                elif et_lower in ep_title:
                     score += 50.0

            # -- Text Content Match (Subtitles) --
            if sub_text and ep.get('name'):
                ep_title = ep['name'].lower()
                st_lower = sub_text.lower()
                
                # Check for exact title in text
                if ep_title in st_lower:
                    score += 100.0
                    reasons.append(f"Title '{ep_title}' found in subtitles")
                else:
                    # Token overlap
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

            # -- Credits Text Match (Higher confidence) --
            if credits_text and ep.get('name'):
                ep_title = ep['name'].lower()
                ct_lower = credits_text.lower()
                
                # Credits are more reliable for title matching
                if ep_title in ct_lower:
                    score += 150.0  # Higher weight than subtitle match
                    reasons.append(f"Title '{ep_title}' found in credits")
                else:
                    # Token overlap in credits
                    tokens = [w for w in re.findall(r"\w+", ep_title) if len(w) > 3]
                    if tokens:
                        found_count = 0
                        for t in tokens:
                            if t in ct_lower:
                                found_count += 1
                        if found_count > 0:
                            ratio = found_count / len(tokens)
                            pts = ratio * 80.0  # Higher weight than subtitle overlap
                            score += pts
                            reasons.append(f"Title words in credits overlap {ratio:.2f}")

            # -- Cast/Crew Match (Very high confidence) --
            if credits_text and ep.get('crew'):
                ct_lower = credits_text.lower()
                crew_matches = 0
                crew_names = []
                
                # Check for writers
                for crew_member in ep.get('crew', []):
                    if crew_member.get('job') in ('Writer', 'Director', 'Executive Producer'):
                        name = crew_member.get('name', '').lower()
                        if name and name in ct_lower:
                            crew_matches += 1
                            crew_names.append(f"{crew_member.get('name')} ({crew_member.get('job')})")
                
                # Check for guest stars
                for cast_member in ep.get('guest_stars', [])[:5]:  # Top 5 guest stars
                    name = cast_member.get('name', '').lower()
                    if name and name in ct_lower:
                        crew_matches += 1
                        crew_names.append(cast_member.get('name'))
                
                if crew_matches > 0:
                    # Very strong signal - each crew match is worth a lot
                    score += crew_matches * 60.0
                    reasons.append(f"Crew/cast match: {', '.join(crew_names[:3])}")

            candidates.append({
                'episode': ep,
                'score': score,
                'reasons': reasons
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates
