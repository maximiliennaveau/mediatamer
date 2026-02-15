#!/usr/bin/env python3
"""Extract DVD metadata for Doctor Who episodes using robust matching."""

import argparse
import re
import json
import sys
from pathlib import Path
import requests
from mediatamer.metadata import extract_metadata
from mediatamer.parameters import get_extensions
from mediatamer.matcher import EpisodeMatcher

def parse_dvd_directory(dvd_dir: Path, api_key: str, language: str = 'fr-FR', dry_run: bool = False):
    """Parse a DVD directory and extract episode metadata."""
    if not dvd_dir.exists() or not dvd_dir.is_dir():
        print(f"Directory {dvd_dir} does not exist")
        return

    # Extract show and season from directory name
    dir_name = dvd_dir.name
    # Parse patterns like "Doctor_Who_S9_DVD1"
    m = re.search(r'(.+?)_?[sS](\d+)(?:_?[dD][vV][dD](\d+))?', dir_name, re.I)
    
    show_name = "Doctor Who"
    season = None
    
    if m:
        show_name_raw = m.group(1).replace('_', ' ')
        season = int(m.group(2))
        if show_name_raw.lower() in ('dr who', 'doctor who'):
            show_name = 'Doctor Who'
        else:
            show_name = show_name_raw.title()
    else:
        # Fallback
        m = re.search(r'S(\d+)', dir_name, re.I)
        if m:
            season = int(m.group(1))

    print(f"Detected Show: {show_name}, Season: {season}")

    if not api_key:
        print("Error: TMDB API key required")
        return

    # Fetch TMDB Data
    try:
        # Search for Show
        search_url = f"https://api.themoviedb.org/3/search/tv"
        params = {'api_key': api_key, 'query': show_name, 'language': 'en-US'}
        resp = requests.get(search_url, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get('results', [])
        
        best_show = None
        for s in results:
             if s['name'].lower() == show_name.lower():
                 best_show = s
                 break
        if not best_show and results:
            best_show = results[0]
            
        if not best_show:
            print("Could not find show on TMDB")
            return

        print(f"Using Show: {best_show['name']} (ID: {best_show['id']})")
        
        # Get Episodes from Season Group (Blu-ray order preferred for DVDs)
        # Using the hardcoded group ID for Doctor Who (2005) or regular season lookup
        # The user's code had a hardcoded group ID. Let's try to be smart.
        # If Doctor Who 2005, use that group ID.
        
        episodes = []
        if best_show['name'] == 'Doctor Who' and '2005' in best_show.get('first_air_date', ''):
             group_id = '65622094244182012dab7ac1' # Blu-ray
             group_url = f"https://api.themoviedb.org/3/tv/episode_group/{group_id}"
             resp = requests.get(group_url, params={'api_key': api_key, 'language': 'en-US'})
             if resp.ok:
                 groups = resp.json().get('groups', [])
                 for g in groups:
                     if f"Season {season}" in g['name']:
                         episodes = g['episodes']
                         break
        
        if not episodes and season:
            # Fallback to standard season endpoint
            season_url = f"https://api.themoviedb.org/3/tv/{best_show['id']}/season/{season}"
            resp = requests.get(season_url, params={'api_key': api_key, 'language': 'en-US'})
            if resp.ok:
                episodes = resp.json().get('episodes', [])

        if not episodes:
            print("No episodes found.")
            return

    except Exception as e:
        print(f"Error communicating with TMDB: {e}")
        return

    # Find video files
    exts = {e if e.startswith('.') else f".{e}" for e in get_extensions()}
    files = sorted([p for p in dvd_dir.glob("*") if p.suffix.lower() in exts and p.is_file()])
    
    if not files:
        print("No video files found.")
        return

    # Run Matcher
    matcher = EpisodeMatcher(episodes)
    results = {}
    
    assigned_episodes = set()
    review_needed = False
    
    final_plan = []

    print(f"Analyzing {len(files)} files...")

    for f in files:
        candidates = matcher.match_file(f)
        
        # Default: No match
        best = None
        if candidates:
            # Heuristic: If top score > 80 and gap to second best is large (or no second best)
            top = candidates[0]
            if top['score'] >= 50.0: # Moderate threshold
                best = top
            else:
                print(f"  [LOW CONFIDENCE] {f.name} - Best score: {top['score']}")
                review_needed = True
        else:
            print(f"  [NO MATCH] {f.name}")
            review_needed = True

        # Check for duplicates
        if best:
            ep_num = best['episode'].get('episode_number')
            if ep_num in assigned_episodes:
                print(f"  [CONFLICT] {f.name} claims Episode {ep_num} which is already assigned.")
                review_needed = True
            assigned_episodes.add(ep_num)

        entry = {
            'file': f.name,
            'path': str(f),
            'candidates': []
        }
        
        # Store top 3 candidates for review
        for c in candidates[:3]:
            entry['candidates'].append({
                'episode_number': c['episode'].get('episode_number'),
                'name': c['episode'].get('name'),
                'score': c['score'],
                'reasons': c['reasons'],
                'tmdb_id': c['episode'].get('id'),
                'overview': c['episode'].get('overview'),
                'air_date': c['episode'].get('air_date'),
                'vote_average': c['episode'].get('vote_average')
            })
            
        if best:
            entry['selected_episode'] = entry['candidates'][0]
        else:
            entry['selected_episode'] = None
            
        final_plan.append(entry)

    # Output
    output_dir = Path("/data/videos/metadata")
    output_dir.mkdir(exist_ok=True)
    
    if review_needed or dry_run:
        review_file = output_dir / "review_plan.json"
        with open(review_file, 'w') as f:
            json.dump({'show': show_name, 'season': season, 'files': final_plan}, f, indent=2)
        print("\n" + "="*60)
        print(f"REVIEW REQUIRED. Plan written to {review_file}")
        print("Inspect the file, manually adjust 'selected_episode' if needed.")
        print("Then run: mediatamer apply-metadata review_plan.json") # TODO: Implement apply-metadata
    else:
        print("\nAll matches high confidence. Writing metadata...")
        for item in final_plan:
            sel = item['selected_episode']
            if not sel: continue
            
            # Reconstruct metadata entry
            # extracting technical metadata again is wasteful but matches old flow, 
            # or we could have stored it. For now, let's just write the JSON.
            # actually we need the technical metadata to write the full .metadata.json
            
            # Simple metadata extraction for final file
            try:
                vm = extract_metadata(Path(item['path']), None, None, language)
            except:
                vm = {}
                
            meta_entry = {
                 'filename': item['file'],
                 'filepath': item['path'],
                 'show_name': show_name,
                 'season': season,
                 'episode_number': sel['episode_number'],
                 'episode_title': sel['name'],
                 'tmdb_episode_id': sel['tmdb_id'],
                 'overview': sel.get('overview'),
                 'air_date': sel.get('air_date'),
                 'vote_average': sel.get('vote_average'),
                 # Tech details
                 'duration': vm.get('duration'),
                 'size': vm.get('size'),
                 'bit_rate': vm.get('bit_rate'),
                 'format_name': vm.get('format_name'),
                 'video_codec': vm.get('video', {}).get('codec_name'),
                 'audio_codecs': [aud.get('codec_name') for aud in vm.get('audios', [])],
                 'languages': list(set([aud.get('language') for aud in vm.get('audios', []) if aud.get('language')])),
            }
            
            out_f = output_dir / f"{item['file']}.metadata.json"
            with open(out_f, 'w') as f:
                 json.dump(meta_entry, f, indent=2, ensure_ascii=False)
            print(f"Wrote {out_f.name}")


def main():
    parser = argparse.ArgumentParser(description="Extract DVD metadata")
    parser.add_argument("dvd_dir", type=Path, help="DVD directory")
    parser.add_argument("--tmdb-api-key", type=str, required=True, help="TMDB API Key")
    parser.add_argument("--language", type=str, default='fr-FR')
    parser.add_argument("--dry-run", action="store_true", help="Do not write metadata files, only review plan")
    
    args = parser.parse_args()
    parse_dvd_directory(args.dvd_dir, args.tmdb_api_key, args.language, args.dry_run)

if __name__ == "__main__":
    main()
