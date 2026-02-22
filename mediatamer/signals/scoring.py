import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from mediatamer.signals.unified import MediaSignals

def parse_disc_track(filename: str) -> Optional[Dict[str, Any]]:
    """Parse DVD disc/track structure from filenames like B2_t04.mkv."""
    m = re.match(r'^([A-Z])(\d+)_t(\d+)', Path(filename).stem, re.I)
    if not m:
        return None
    return {
        'disc': m.group(1).upper(),
        'track': int(m.group(2)),
        'global_index': int(m.group(3)),
    }

def score_episode_match(
    ep: Dict[str, Any],
    file_path: Path,
    media_signals: MediaSignals,
    sub_text: Optional[str] = None,
    credits_text: Optional[str] = None,
    context_hints: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Score a single TMDB episode against a file's signals."""
    score = 0.0
    reasons = []
    
    duration = media_signals.duration
    embedded_title = media_signals.embedded_title
    disc_info = parse_disc_track(file_path.name)
    
    # 1. Duration Match
    ep_runtime = ep.get('runtime')
    if duration and ep_runtime:
        ep_duration_sec = ep_runtime * 60
        diff = abs(duration - ep_duration_sec)
        if diff < 60:
            score += 50.0
            reasons.append(f"Duration match ({diff:.0f}s diff)")
        elif diff < 300:
            score += 20.0
            reasons.append(f"Loose duration match ({diff:.0f}s diff)")
        elif diff > 900:
            score -= 100.0
            reasons.append(f"Duration mismatch ({diff/60:.1f}m diff)")
        elif diff > 600:
            score -= 50.0

    # 1b. Chapters Signal
    has_chapters = media_signals.has_chapters
    chapter_count = len(media_signals.chapters)
    if has_chapters:
        if 4 <= chapter_count <= 8:
            score += 20.0
            reasons.append(f"Chapter count ({chapter_count}) consistent with single episode")
        elif chapter_count > 12 and media_signals.is_multi_episode:
            score += 40.0
            reasons.append(f"High chapter count ({chapter_count}) suggesting multi-episode file")

    # 2. Context Hints
    if context_hints:
        is_likely_episode = context_hints.get('is_likely_episode')
        last_episode_matched = context_hints.get('last_episode_matched')
        has_global_indices = context_hints.get('has_global_indices')
        target_season = context_hints.get('season_number')
        dvd_number = context_hints.get('dvd_number')

        if is_likely_episode is True:
            if int(ep.get('season_number', -1)) == 0:
                score -= 100.0
                reasons.append("Penalizing Season 0 for likely main episode file")
            elif target_season is not None and int(ep.get('season_number', -1)) == target_season:
                score += 30.0
                reasons.append(f"Rewarding Season {target_season} for likely main episode file")
        elif is_likely_episode is False:
            if int(ep.get('season_number', -1)) == 0:
                score += 50.0
                reasons.append("Rewarding Season 0 for likely bonus file")
            elif target_season is not None and int(ep.get('season_number', -1)) == target_season:
                score -= 50.0
                reasons.append(f"Penalizing Season {target_season} for likely bonus file")

        ep_num = ep.get('episode_number', -1)
        
        # Relative Sequence Matching (Very Strong)
        if last_episode_matched is not None:
            if ep_num == last_episode_matched + 1:
                score += 60.0
                reasons.append(f"Perfect relative sequence (last E{last_episode_matched} -> E{ep_num})")
            elif ep_num > last_episode_matched:
                score += 30.0
                reasons.append(f"Forward episode sequence (E{ep_num} > last E{last_episode_matched})")
            elif ep_num <= last_episode_matched:
                score -= 60.0 # Strict penalty for out of order
                reasons.append(f"Penalizing out-of-order sequence (E{ep_num} <= last E{last_episode_matched})")

        # Global/Disc Track Index Matching
        if disc_info:
            global_idx = disc_info.get('global_index')
            if global_idx is not None:
                expected_ep_abs = global_idx + 1
                
                if ep_num == expected_ep_abs:
                    score += 150.0 if has_global_indices else 40.0
                    reasons.append(f"Global index match (t{global_idx:02d} -> E{ep_num})")
                elif has_global_indices:
                    # If we are on DVD 1, we expect absolute match
                    if dvd_number is None or dvd_number <= 1:
                        score -= 100.0
                        reasons.append(f"Global index mismatch on DVD1 (expected E{expected_ep_abs}, got E{ep_num})")
                    else:
                        # On DVD > 1, tracks might reset or have weird offsets.
                        # We don't penalize as heavily if it's the first file and we don't have last_ep
                        if last_episode_matched is None:
                            score -= 20.0
                            reasons.append(f"Gentle penalty for global mismatch on DVD{dvd_number} (first file)")
                        else:
                            # If we have last_ep, we care more about relative sequence than absolute track match
                            pass

    # 3. Filename 'Extra' detection
    if 'extra' in file_path.name.lower() and 'extra' in ep.get('name', '').lower():
        score += 40.0
        reasons.append("Filename and Episode both contain 'Extra'")

    # 4. Text Matches
    def score_text(text, weight, source_name):
        nonlocal score
        if not text or not ep.get('name'): return
        title = ep['name'].lower()
        t_lower = text.lower()
        if title in t_lower:
            score += weight
            reasons.append(f"Title '{title}' found in {source_name}")
        else:
            tokens = [w for w in re.findall(r"\w+", title) if len(w) > 3]
            if tokens:
                found = sum(1 for t in tokens if t in t_lower)
                if found:
                    ratio = found / len(tokens)
                    score += ratio * (weight * 0.6)
                    reasons.append(f"Title words in {source_name} overlap {ratio:.2f}")

    score_text(embedded_title, 100.0, "MKV tags")
    score_text(sub_text, 100.0, "subtitles")
    score_text(credits_text, 150.0, "credits")

    # 5. Cast/Crew Match
    if credits_text and (ep.get('crew') or ep.get('guest_stars')):
        ct_lower = credits_text.lower()
        crew_matches = 0
        crew_names = []
        for crew in ep.get('crew', []):
            if crew.get('job') in ('Writer', 'Director', 'Executive Producer'):
                name = crew.get('name', '').lower()
                if name and name in ct_lower:
                    crew_matches += 1
                    crew_names.append(f"{crew.get('name')} ({crew.get('job')})")
        for cast in ep.get('guest_stars', [])[:5]:
            name = cast.get('name', '').lower()
            if name and name in ct_lower:
                crew_matches += 1
                crew_names.append(cast.get('name'))
        if crew_matches > 0:
            score += crew_matches * 60.0
            reasons.append(f"Crew/cast match: {', '.join(crew_names[:3])}")

    return {'score': score, 'reasons': reasons}
